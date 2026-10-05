"""The only legal task status transitions in the Phase 2 engine."""

from datetime import UTC, datetime

from lucifer.core.tasks import TaskRecord, TaskStatus

ALLOWED: dict[TaskStatus, frozenset[TaskStatus]] = {
    TaskStatus.PENDING: frozenset({TaskStatus.READY, TaskStatus.BLOCKED, TaskStatus.CANCELLED}),
    TaskStatus.READY: frozenset({TaskStatus.RUNNING, TaskStatus.BLOCKED, TaskStatus.CANCELLED}),
    TaskStatus.RUNNING: frozenset(
        {
            TaskStatus.READY,
            TaskStatus.BLOCKED,
            TaskStatus.COMPLETED,
            TaskStatus.FAILED,
            TaskStatus.CANCELLED,
        }
    ),
    TaskStatus.WAITING_APPROVAL: frozenset(),
    TaskStatus.BLOCKED: frozenset(),
    TaskStatus.FAILED: frozenset(),
    TaskStatus.COMPLETED: frozenset(),
    TaskStatus.CANCELLED: frozenset(),
}


def transition(
    task: TaskRecord,
    target: TaskStatus,
    *,
    output: dict[str, object] | None = None,
    error: str | None = None,
) -> TaskRecord:
    if target not in ALLOWED[task.status]:
        raise ValueError(f"invalid task transition: {task.status} -> {target}")
    now = datetime.now(UTC)
    changes: dict[str, object] = {"status": target}
    if target == TaskStatus.RUNNING:
        changes["started_at"] = now
        changes["error"] = None
    if target in {TaskStatus.BLOCKED, TaskStatus.FAILED, TaskStatus.CANCELLED}:
        changes["error"] = (error or target.value)[:4000]
        changes["completed_at"] = now
    if target == TaskStatus.COMPLETED:
        changes["output"] = output if output is not None else {}
        changes["completed_at"] = now
        changes["error"] = None
    if target == TaskStatus.READY and task.status == TaskStatus.RUNNING:
        changes["retries"] = task.retries + 1
        changes["error"] = (error or "retry requested")[:4000]
    return task.model_copy(update=changes)
