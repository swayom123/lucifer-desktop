"""SQLAlchemy persistence for Phase 1 tasks."""

import os
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, create_engine, select, update
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from lucifer.core.lifecycle import ALLOWED
from lucifer.core.tasks import RiskLevel, TaskCreate, TaskRecord, TaskStatus


class Base(DeclarativeBase):
    pass


class TaskRow(Base):
    __tablename__ = "tasks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    trace_id: Mapped[str] = mapped_column(String(36), index=True)
    parent_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("tasks.id"))
    objective: Mapped[str] = mapped_column(String(4000))
    description: Mapped[str] = mapped_column(String(8000))
    assigned_agent: Mapped[str | None] = mapped_column(String(200))
    dependencies: Mapped[list[str]] = mapped_column(JSON)
    required_tools: Mapped[list[str]] = mapped_column(JSON)
    risk_level: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(30), index=True)
    input: Mapped[dict[str, Any]] = mapped_column(JSON)
    output: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    retries: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(String(4000))


def make_engine(path: Path) -> Engine:
    directory_is_new = not path.parent.exists()
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if os.name == "posix" and directory_is_new:
        path.parent.chmod(0o700)
    engine = create_engine(f"sqlite:///{path}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    if os.name == "posix":
        path.chmod(0o600)
    return engine


class SqlTaskRepository:
    def __init__(self, sessions: sessionmaker[Session]) -> None:
        self._sessions = sessions

    @contextmanager
    def _session(self) -> Iterator[Session]:
        with self._sessions() as session:
            yield session

    def create(self, request: TaskCreate) -> TaskRecord:
        record = TaskRecord.model_validate(request.model_dump())
        row = TaskRow(
            id=str(record.id),
            trace_id=str(record.trace_id),
            parent_id=None,
            objective=record.objective,
            description=record.description,
            assigned_agent=None,
            dependencies=[],
            required_tools=[],
            risk_level=record.risk_level.value,
            status=record.status.value,
            input=record.input,
            output=None,
            created_at=record.created_at,
            started_at=None,
            completed_at=None,
            retries=0,
            error=None,
        )
        with self._session() as session:
            session.add(row)
            session.commit()
        return record

    def get(self, task_id: UUID) -> TaskRecord | None:
        with self._session() as session:
            row = session.get(TaskRow, str(task_id))
            if row is None:
                return None
            return self._record(row)

    def create_children(self, parent_id: UUID, children: list[TaskRecord]) -> None:
        identifiers = {child.id for child in children}
        if len(identifiers) != len(children):
            raise ValueError("duplicate child IDs")
        with self._session() as session, session.begin():
            parent = session.get(TaskRow, str(parent_id))
            if parent is None:
                raise ValueError("parent task does not exist")
            if session.scalar(select(TaskRow.id).where(TaskRow.parent_id == str(parent_id))):
                raise ValueError("plan already persisted")
            for child in children:
                if child.parent_id != parent_id:
                    raise ValueError("child parent mismatch")
                if str(child.trace_id) != parent.trace_id:
                    raise ValueError("child trace mismatch")
                if child.status != TaskStatus.PENDING or child.required_tools:
                    raise ValueError("child must be pending without tools")
                if any(dep not in identifiers or dep == child.id for dep in child.dependencies):
                    raise ValueError("invalid child dependency")
                session.add(self._row(child))

    def children(self, parent_id: UUID) -> list[TaskRecord]:
        with self._session() as session:
            rows = session.scalars(
                select(TaskRow)
                .where(TaskRow.parent_id == str(parent_id))
                .order_by(TaskRow.created_at)
            ).all()
            return [self._record(row) for row in rows]

    def save(self, task: TaskRecord, expected_status: TaskStatus) -> None:
        if task.status not in ALLOWED[expected_status]:
            raise ValueError("invalid persisted task transition")
        with self._session() as session, session.begin():
            result = session.connection().execute(
                update(TaskRow)
                .where(TaskRow.id == str(task.id), TaskRow.status == expected_status.value)
                .values(
                    status=task.status.value,
                    assigned_agent=task.assigned_agent,
                    output=task.output,
                    started_at=task.started_at,
                    completed_at=task.completed_at,
                    retries=task.retries,
                    error=task.error,
                )
            )
            if result.rowcount != 1:
                raise ValueError("task state changed concurrently or task is missing")

    @staticmethod
    def _row(record: TaskRecord) -> TaskRow:
        return TaskRow(
            id=str(record.id),
            trace_id=str(record.trace_id),
            parent_id=str(record.parent_id) if record.parent_id else None,
            objective=record.objective,
            description=record.description,
            assigned_agent=record.assigned_agent,
            dependencies=[str(value) for value in record.dependencies],
            required_tools=record.required_tools,
            risk_level=record.risk_level.value,
            status=record.status.value,
            input=record.input,
            output=record.output,
            created_at=record.created_at,
            started_at=record.started_at,
            completed_at=record.completed_at,
            retries=record.retries,
            error=record.error,
        )

    @staticmethod
    def _record(row: TaskRow) -> TaskRecord:
        def aware(value: datetime | None) -> datetime | None:
            return value.replace(tzinfo=UTC) if value and value.tzinfo is None else value

        return TaskRecord(
            id=UUID(row.id),
            trace_id=UUID(row.trace_id),
            parent_id=UUID(row.parent_id) if row.parent_id else None,
            objective=row.objective,
            description=row.description,
            assigned_agent=row.assigned_agent,
            dependencies=[UUID(value) for value in row.dependencies],
            required_tools=row.required_tools,
            risk_level=RiskLevel(row.risk_level),
            status=TaskStatus(row.status),
            input=row.input,
            output=row.output,
            created_at=aware(row.created_at) or row.created_at,
            started_at=aware(row.started_at),
            completed_at=aware(row.completed_at),
            retries=row.retries,
            error=row.error,
        )
