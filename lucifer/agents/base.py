"""Agent contract. Agents will be wired into the scheduler in Phase 2."""

from enum import StrEnum
from typing import Any, Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class AgentStatus(StrEnum):
    IDLE = "IDLE"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class RetryPolicy(BaseModel):
    max_attempts: int = Field(default=1, ge=1, le=10)
    delay_seconds: float = Field(default=0, ge=0, le=60)


class AgentDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    description: str
    capabilities: frozenset[str] = frozenset()
    allowed_tools: frozenset[str] = frozenset()
    permissions: frozenset[str] = frozenset()
    model_class: str | None = None
    timeout_seconds: float = Field(default=30, gt=0)
    retry_policy: RetryPolicy = Field(default_factory=RetryPolicy)


class AgentInput(BaseModel):
    task_id: UUID
    trace_id: UUID
    payload: dict[str, Any] = Field(default_factory=dict)


class AgentOutput(BaseModel):
    trace_id: UUID
    status: AgentStatus
    payload: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None


class BaseAgent(Protocol):
    @property
    def definition(self) -> AgentDefinition: ...

    async def run(self, task: AgentInput) -> AgentOutput: ...
