"""HTTP boundary for task submission and inspection."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated
from uuid import UUID

from fastapi import Depends, FastAPI, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import sessionmaker

from lucifer.config.settings import Settings
from lucifer.core.tasks import TaskCreate, TaskRecord
from lucifer.observability.logging import configure_logging
from lucifer.storage.database import SqlTaskRepository, make_engine
from lucifer.storage.repository import TaskRepository


class HealthResponse(BaseModel):
    status: str


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.load()
    configure_logging(settings.log_level)
    repository: TaskRepository | None = None

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        nonlocal repository
        engine = make_engine(settings.database_path)
        repository = SqlTaskRepository(sessionmaker(engine, expire_on_commit=False))
        try:
            yield
        finally:
            repository = None
            engine.dispose()

    app = FastAPI(title="Lucifer Foundation API", version="0.1.0", lifespan=lifespan)

    async def get_repository() -> TaskRepository:
        if repository is None:
            raise RuntimeError("Application lifespan has not started")
        return repository

    Store = Annotated[TaskRepository, Depends(get_repository)]

    @app.get("/health", response_model=HealthResponse)
    async def health() -> HealthResponse:
        return HealthResponse(status="ok")

    @app.post("/tasks", response_model=TaskRecord, status_code=status.HTTP_201_CREATED)
    async def create_task(request: TaskCreate, store: Store) -> TaskRecord:
        task = store.create(request)
        logging.getLogger("lucifer.api").info(
            "task.created", extra={"trace_id": str(task.trace_id)}
        )
        return task

    @app.get("/tasks/{task_id}", response_model=TaskRecord)
    async def get_task(task_id: UUID, store: Store) -> TaskRecord:
        task = store.get(task_id)
        if task is None:
            raise HTTPException(status_code=404, detail="Task not found")
        return task

    return app


app = create_app()
