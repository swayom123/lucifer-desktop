"""Bounded single-run task graph coordinator."""

import asyncio
import logging
from uuid import UUID, uuid4

from lucifer.agents.base import AgentInput, AgentOutput
from lucifer.core.lifecycle import transition
from lucifer.core.planner import Planner, TaskPlan
from lucifer.core.router import AgentRouter
from lucifer.core.tasks import TaskRecord, TaskStatus
from lucifer.core.verifier import Verifier
from lucifer.storage.repository import TaskRepository


class Orchestrator:
    def __init__(
        self,
        repository: TaskRepository,
        planner: Planner,
        router: AgentRouter,
        verifier: Verifier,
    ) -> None:
        self.repository = repository
        self.planner = planner
        self.router = router
        self.verifier = verifier
        self.log = logging.getLogger("lucifer.orchestrator")
        self._locks: dict[UUID, asyncio.Lock] = {}

    async def run(self, goal_id: UUID) -> TaskRecord:
        lock = self._locks.setdefault(goal_id, asyncio.Lock())
        async with lock:
            goal = self.repository.get(goal_id)
            if goal is None:
                raise KeyError(goal_id)
            if goal.parent_id is not None or goal.status != TaskStatus.PENDING:
                raise ValueError("only a pending root task can be started")
            goal = self._move(goal, TaskStatus.READY)
            goal = self._move(goal, TaskStatus.RUNNING)
            try:
                plan = await self.planner.plan(goal)
                # A custom planner must meet the same contract as ModelPlanner.
                plan = TaskPlan.model_validate(plan.model_dump())
                children = self._materialize(goal, plan)
                self.repository.create_children(goal.id, children)
                await self._drive(goal.id)
                final_children = self.repository.children(goal.id)
                statuses = {child.status for child in final_children}
                if statuses == {TaskStatus.COMPLETED}:
                    output: dict[str, object] = {
                        "tasks": [
                            {
                                "id": str(child.id),
                                "objective": child.objective,
                                "output": child.output,
                            }
                            for child in final_children
                        ]
                    }
                    goal = self._move(goal, TaskStatus.COMPLETED, output=output)
                elif TaskStatus.FAILED in statuses:
                    goal = self._move(goal, TaskStatus.FAILED, error="one or more subtasks failed")
                else:
                    goal = self._move(
                        goal, TaskStatus.BLOCKED, error="one or more subtasks blocked"
                    )
            except asyncio.CancelledError:
                for child in self.repository.children(goal.id):
                    if child.status in {TaskStatus.PENDING, TaskStatus.READY, TaskStatus.RUNNING}:
                        self._move(child, TaskStatus.CANCELLED, error="goal cancelled")
                self._move(goal, TaskStatus.CANCELLED, error="goal cancelled")
                raise
            except Exception as exc:  # noqa: BLE001 - mark planner or coordinator failure
                self.log.warning(
                    "goal.failed",
                    extra={"trace_id": str(goal.trace_id), "error_class": type(exc).__name__},
                )
                goal = self._move(
                    goal, TaskStatus.FAILED, error=f"orchestration error: {type(exc).__name__}"
                )
            finally:
                self._locks.pop(goal_id, None)
            return goal

    def _materialize(self, goal: TaskRecord, plan: TaskPlan) -> list[TaskRecord]:
        identifiers = {item.key: uuid4() for item in plan.tasks}
        return [
            TaskRecord(
                id=identifiers[item.key],
                trace_id=goal.trace_id,
                parent_id=goal.id,
                objective=item.objective,
                description=item.description,
                dependencies=[identifiers[key] for key in item.dependencies],
                required_tools=item.required_tools,
                input={"plan_key": item.key, "capability": item.capability, "payload": item.input},
            )
            for item in plan.tasks
        ]

    async def _drive(self, goal_id: UUID) -> None:
        # A valid flat graph has at most 32 tasks; each pass changes at least one status.
        for _ in range(65):
            children = self.repository.children(goal_id)
            by_id = {child.id: child for child in children}
            changed = False
            for child in children:
                if child.status != TaskStatus.PENDING:
                    continue
                states = [by_id[dep].status for dep in child.dependencies]
                if any(
                    state in {TaskStatus.BLOCKED, TaskStatus.FAILED, TaskStatus.CANCELLED}
                    for state in states
                ):
                    self._move(child, TaskStatus.BLOCKED, error="dependency did not complete")
                    changed = True
                elif all(state == TaskStatus.COMPLETED for state in states):
                    self._move(child, TaskStatus.READY)
                    changed = True
            ready = [
                child
                for child in self.repository.children(goal_id)
                if child.status == TaskStatus.READY
            ]
            for child in ready:
                current = {item.id: item for item in self.repository.children(goal_id)}
                await self._execute(child, current)
                changed = True
            if not changed:
                break
        for child in self.repository.children(goal_id):
            if child.status in {TaskStatus.PENDING, TaskStatus.READY, TaskStatus.RUNNING}:
                self._move(child, TaskStatus.BLOCKED, error="scheduler made no progress")

    async def _execute(self, task: TaskRecord, children: dict[UUID, TaskRecord]) -> None:
        capability = str(task.input["capability"])
        from lucifer.core.planner import PlanTask

        route_request = PlanTask(
            key=str(task.input["plan_key"]),
            objective=task.objective,
            capability=capability,
            required_tools=task.required_tools,
        )
        agent = self.router.route(route_request)
        if agent is None:
            self._move(task, TaskStatus.BLOCKED, error=f"no agent for capability: {capability}")
            return
        task = task.model_copy(update={"assigned_agent": agent.definition.id})
        max_attempts = agent.definition.retry_policy.max_attempts
        for attempt in range(max_attempts):
            task = self._move(task, TaskStatus.RUNNING)
            error: str | None = None
            try:
                dependency_output = {
                    str(dep): children[dep].output or {} for dep in task.dependencies
                }
                result: AgentOutput = await asyncio.wait_for(
                    agent.run(
                        AgentInput(
                            task_id=task.id,
                            trace_id=task.trace_id,
                            payload={
                                "input": task.input["payload"],
                                "dependencies": dependency_output,
                            },
                        )
                    ),
                    timeout=agent.definition.timeout_seconds,
                )
                verdict = await asyncio.wait_for(
                    self.verifier.verify(task, result),
                    timeout=agent.definition.timeout_seconds,
                )
                if verdict.ok:
                    self._move(task, TaskStatus.COMPLETED, output=result.payload)
                    return
                error = verdict.reason or "verification failed"
            except TimeoutError:
                error = "agent or verifier timed out"
            except Exception as exc:  # noqa: BLE001 - isolate untrusted agent failures
                error = f"agent error: {type(exc).__name__}"
            if attempt + 1 < max_attempts:
                task = self._move(task, TaskStatus.READY, error=error)
                await asyncio.sleep(agent.definition.retry_policy.delay_seconds)
            else:
                self._move(task, TaskStatus.FAILED, error=error)

    def _move(
        self,
        task: TaskRecord,
        target: TaskStatus,
        *,
        output: dict[str, object] | None = None,
        error: str | None = None,
    ) -> TaskRecord:
        updated = transition(task, target, output=output, error=error)
        self.repository.save(updated, expected_status=task.status)
        self.log.info(
            "task.transition",
            extra={"trace_id": str(task.trace_id), "task_id": str(task.id), "status": target.value},
        )
        return updated
