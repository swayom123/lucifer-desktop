"""Phase 1 API, persistence, schema and registry checks."""

import asyncio
from pathlib import Path
from uuid import UUID

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError
from sqlalchemy.orm import sessionmaker

from lucifer.apps.api.app import create_app
from lucifer.config.settings import Settings
from lucifer.core.tasks import RiskLevel, TaskCreate
from lucifer.storage.database import SqlTaskRepository, make_engine
from lucifer.tools.registry import ToolDefinition, ToolRegistry


def test_task_api_persists_across_app_instances(tmp_path: Path) -> None:
    async def run() -> None:
        settings = Settings(database_path=tmp_path / "tasks.db")
        app = create_app(settings)
        async with (
            app.router.lifespan_context(app),
            AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client,
        ):
            assert (await client.get("/health")).json() == {"status": "ok"}
            response = await client.post("/tasks", json={"objective": "Inspect repository"})
            assert response.status_code == 201
            task = response.json()
            assert task["status"] == "PENDING"
            assert UUID(task["trace_id"])
        app = create_app(settings)
        async with (
            app.router.lifespan_context(app),
            AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client,
        ):
            assert (await client.get(f"/tasks/{task['id']}")).json() == task
            assert (await client.get(f"/tasks/{UUID(int=0)}")).status_code == 404

    asyncio.run(run())


def test_task_input_validation(tmp_path: Path) -> None:
    async def run() -> None:
        app = create_app(Settings(database_path=tmp_path / "tasks.db"))
        async with (
            app.router.lifespan_context(app),
            AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client,
        ):
            assert (await client.post("/tasks", json={"objective": "   "})).status_code == 422
            assert (
                await client.post("/tasks", json={"objective": "x", "status": "COMPLETED"})
            ).status_code == 422
            assert (await client.get("/tasks/not-a-uuid")).status_code == 422

    asyncio.run(run())


def test_repository_round_trip(tmp_path: Path) -> None:
    engine = make_engine(tmp_path / "nested" / "tasks.db")
    repo = SqlTaskRepository(sessionmaker(engine))
    task = repo.create(TaskCreate(objective="Research", input={"topic": "edge AI"}))
    assert repo.get(task.id) == task
    engine.dispose()


def test_registry_rejects_duplicates_and_has_no_execute() -> None:
    class ExampleTool:
        definition = ToolDefinition(
            name="example",
            description="Metadata only",
            input_schema={},
            output_schema={},
            risk_level=RiskLevel.LOW,
            timeout_seconds=1,
        )

    registry = ToolRegistry()
    registry.register(ExampleTool())
    assert registry.get("example").definition.name == "example"
    with pytest.raises(ValueError, match="duplicate"):
        registry.register(ExampleTool())
    assert not hasattr(registry, "execute")


def test_schema_rejects_invalid_tool_and_task() -> None:
    with pytest.raises(ValidationError):
        ToolDefinition(
            name="../shell",
            description="bad",
            input_schema={},
            output_schema={},
            risk_level=RiskLevel.LOW,
            timeout_seconds=1,
        )
    with pytest.raises(ValidationError):
        TaskCreate(objective="")
