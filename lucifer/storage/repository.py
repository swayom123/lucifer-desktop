"""Persistence boundary used by the API and future orchestrator."""

from typing import Protocol
from uuid import UUID

from lucifer.core.tasks import TaskCreate, TaskRecord, TaskStatus


class TaskRepository(Protocol):
    def create(self, request: TaskCreate) -> TaskRecord: ...

    def get(self, task_id: UUID) -> TaskRecord | None: ...

    def create_children(self, parent_id: UUID, children: list[TaskRecord]) -> None: ...

    def children(self, parent_id: UUID) -> list[TaskRecord]: ...

    def save(self, task: TaskRecord, expected_status: TaskStatus) -> None: ...
