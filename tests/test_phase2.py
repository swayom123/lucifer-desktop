"""Focused Phase 2 graph, routing, lifecycle, retry, and failure tests."""

import asyncio
from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy.orm import sessionmaker

from lucifer.agents.base import AgentDefinition, AgentInput, AgentOutput, AgentStatus, RetryPolicy
from lucifer.core.lifecycle import ALLOWED, transition
from lucifer.core.orchestrator import Orchestrator
from lucifer.core.planner import ModelPlanner, PlanTask, TaskPlan
from lucifer.core.router import AgentRouter
from lucifer.core.tasks import TaskCreate, TaskRecord, TaskStatus
from lucifer.core.verifier import StructuralVerifier
from lucifer.models.provider import ModelResponse
from lucifer.storage.database import SqlTaskRepository, make_engine


class FixedPlanner:
    def __init__(self, plan: TaskPlan) -> None:
        self.task_plan = plan

    async def plan(self, goal: TaskRecord) -> TaskPlan:
        return self.task_plan


class FakeAgent:
    def __init__(
        self,
        capability: str,
        outcomes: list[str] | None = None,
        attempts: int = 1,
        timeout: float = 1,
    ) -> None:
        self.definition = AgentDefinition(
            id=capability,
            name=capability,
            description="test agent",
            capabilities=frozenset({capability}),
            retry_policy=RetryPolicy(max_attempts=attempts),
            timeout_seconds=timeout,
        )
        self.outcomes = outcomes or ["ok"]
        self.calls: list[AgentInput] = []

    async def run(self, task: AgentInput) -> AgentOutput:
        self.calls.append(task)
        outcome = self.outcomes[min(len(self.calls) - 1, len(self.outcomes) - 1)]
        if outcome == "timeout":
            await asyncio.sleep(0.1)
        if outcome == "error":
            raise RuntimeError("temporary failure")
        if outcome == "bad_trace":
            return AgentOutput(trace_id=uuid4(), status=AgentStatus.COMPLETED)
        if outcome == "bad_payload":
            return AgentOutput(
                trace_id=task.trace_id, status=AgentStatus.COMPLETED, payload={"bad": {1}}
            )
        return AgentOutput(
            trace_id=task.trace_id,
            status=AgentStatus.COMPLETED,
            payload={"task": str(task.task_id)},
        )


def repository(tmp_path: Path) -> SqlTaskRepository:
    return SqlTaskRepository(sessionmaker(make_engine(tmp_path / "phase2.db")))


def plan(*items: PlanTask) -> TaskPlan:
    return TaskPlan(tasks=list(items))


def execute(
    tmp_path: Path, task_plan: TaskPlan, agents: list[FakeAgent]
) -> tuple[SqlTaskRepository, TaskRecord]:
    store = repository(tmp_path)
    goal = store.create(TaskCreate(objective="Run a goal"))
    engine = Orchestrator(store, FixedPlanner(task_plan), AgentRouter(agents), StructuralVerifier())
    return store, asyncio.run(engine.run(goal.id))


@pytest.mark.parametrize(
    "tasks",
    [
        [PlanTask(key="a", objective="a", capability="work", dependencies=["missing"])],
        [PlanTask(key="a", objective="a", capability="work", dependencies=["a"])],
        [
            PlanTask(key="a", objective="a", capability="work"),
            PlanTask(key="a", objective="b", capability="work"),
        ],
        [
            PlanTask(key="a", objective="a", capability="work", dependencies=["b"]),
            PlanTask(key="b", objective="b", capability="work", dependencies=["a"]),
        ],
        [PlanTask(key="a", objective="a", capability="work", required_tools=["shell"])],
    ],
)
def test_plan_rejects_invalid_graphs(tasks: list[PlanTask]) -> None:
    with pytest.raises(ValidationError):
        TaskPlan(tasks=tasks)


def test_transitions_are_explicit_and_terminal() -> None:
    task = TaskRecord(objective="x")
    assert set(ALLOWED) == set(TaskStatus)
    ready = transition(task, TaskStatus.READY)
    running = transition(ready, TaskStatus.RUNNING)
    retried = transition(running, TaskStatus.READY, error="retry")
    assert retried.retries == 1
    assert retried.error == "retry"
    done = transition(running, TaskStatus.COMPLETED, output={"ok": True})
    assert done.completed_at is not None
    with pytest.raises(ValueError, match="invalid task transition"):
        transition(done, TaskStatus.RUNNING)


def test_dependency_order_and_persistence(tmp_path: Path) -> None:
    first = FakeAgent("collect")
    second = FakeAgent("summarize")
    store, goal = execute(
        tmp_path,
        plan(
            PlanTask(
                key="summary",
                objective="Summarize",
                capability="summarize",
                dependencies=["source"],
            ),
            PlanTask(key="source", objective="Collect", capability="collect"),
        ),
        [second, first],
    )
    children = store.children(goal.id)
    assert goal.status == TaskStatus.COMPLETED
    assert all(child.status == TaskStatus.COMPLETED for child in children)
    assert second.calls[0].payload["dependencies"] == {
        str(first.calls[0].task_id): {"task": str(first.calls[0].task_id)}
    }
    assert store.get(goal.id) == goal


def test_retry_is_bounded(tmp_path: Path) -> None:
    agent = FakeAgent("work", outcomes=["error", "ok"], attempts=2)
    store, goal = execute(
        tmp_path, plan(PlanTask(key="do", objective="Do", capability="work")), [agent]
    )
    assert goal.status == TaskStatus.COMPLETED
    assert store.children(goal.id)[0].retries == 1
    assert len(agent.calls) == 2


@pytest.mark.parametrize("outcome", ["error", "timeout", "bad_trace", "bad_payload"])
def test_agent_or_verifier_failure_exhausts_retries(tmp_path: Path, outcome: str) -> None:
    agent = FakeAgent("work", outcomes=[outcome], attempts=2, timeout=0.01)
    store, goal = execute(
        tmp_path, plan(PlanTask(key="do", objective="Do", capability="work")), [agent]
    )
    assert goal.status == TaskStatus.FAILED
    child = store.children(goal.id)[0]
    assert child.status == TaskStatus.FAILED
    assert child.retries == 1
    assert len(agent.calls) == 2


def test_missing_agent_blocks_dependents(tmp_path: Path) -> None:
    store, goal = execute(
        tmp_path,
        plan(
            PlanTask(key="a", objective="A", capability="missing"),
            PlanTask(key="b", objective="B", capability="work", dependencies=["a"]),
        ),
        [FakeAgent("work")],
    )
    assert goal.status == TaskStatus.BLOCKED
    assert {child.status for child in store.children(goal.id)} == {TaskStatus.BLOCKED}


def test_failed_dependency_blocks_child(tmp_path: Path) -> None:
    follower = FakeAgent("follow")
    store, goal = execute(
        tmp_path,
        plan(
            PlanTask(key="a", objective="A", capability="fail"),
            PlanTask(key="b", objective="B", capability="follow", dependencies=["a"]),
        ),
        [FakeAgent("fail", outcomes=["error"]), follower],
    )
    assert goal.status == TaskStatus.FAILED
    assert [child.status for child in store.children(goal.id)] == [
        TaskStatus.FAILED,
        TaskStatus.BLOCKED,
    ]
    assert follower.calls == []


def test_repository_rejects_stale_and_illegal_updates(tmp_path: Path) -> None:
    store = repository(tmp_path)
    goal = store.create(TaskCreate(objective="x"))
    ready = transition(goal, TaskStatus.READY)
    store.save(ready, TaskStatus.PENDING)
    with pytest.raises(ValueError, match="concurrently"):
        store.save(ready, TaskStatus.PENDING)
    with pytest.raises(ValueError, match="invalid persisted"):
        store.save(ready.model_copy(update={"status": TaskStatus.COMPLETED}), TaskStatus.READY)


def test_cancellation_marks_goal_and_child(tmp_path: Path) -> None:
    class SlowAgent(FakeAgent):
        async def run(self, task: AgentInput) -> AgentOutput:
            self.calls.append(task)
            await asyncio.sleep(10)
            return AgentOutput(trace_id=task.trace_id, status=AgentStatus.COMPLETED)

    async def run() -> None:
        store = repository(tmp_path)
        goal = store.create(TaskCreate(objective="cancel me"))
        agent = SlowAgent("slow")
        engine = Orchestrator(
            store,
            FixedPlanner(plan(PlanTask(key="a", objective="A", capability="slow"))),
            AgentRouter([agent]),
            StructuralVerifier(),
        )
        operation = asyncio.create_task(engine.run(goal.id))
        for _ in range(100):
            if agent.calls:
                break
            await asyncio.sleep(0.001)
        assert agent.calls
        operation.cancel()
        with pytest.raises(asyncio.CancelledError):
            await operation
        assert store.get(goal.id).status == TaskStatus.CANCELLED
        assert store.children(goal.id)[0].status == TaskStatus.CANCELLED

    asyncio.run(run())


def test_router_rejects_duplicate_ids_and_selects_stably() -> None:
    agent = FakeAgent("work")
    router = AgentRouter([agent])
    with pytest.raises(ValueError, match="duplicate agent"):
        router.register(FakeAgent("work"))
    assert router.route(PlanTask(key="a", objective="A", capability="work")) is agent
    assert router.route(PlanTask(key="b", objective="B", capability="missing")) is None


def test_malformed_model_plan_fails_goal(tmp_path: Path) -> None:
    class BadProvider:
        async def complete(self, request: object) -> ModelResponse:
            return ModelResponse(
                content='{"tasks": [{"key": "a", "required_tools": ["shell"]}]}', model="fake"
            )

    store = repository(tmp_path)
    goal = store.create(TaskCreate(objective="Plan safely"))
    result = asyncio.run(
        Orchestrator(store, ModelPlanner(BadProvider()), AgentRouter(), StructuralVerifier()).run(
            goal.id
        )
    )
    assert result.status == TaskStatus.FAILED
    assert store.children(goal.id) == []
