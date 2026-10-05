"""Separate verification contract for agent output."""

import json
from typing import Protocol

from pydantic import BaseModel

from lucifer.agents.base import AgentOutput, AgentStatus
from lucifer.core.tasks import TaskRecord


class Verification(BaseModel):
    ok: bool
    reason: str | None = None


class Verifier(Protocol):
    async def verify(self, task: TaskRecord, result: AgentOutput) -> Verification: ...


class StructuralVerifier:
    """Checks shape and trace only; domain-specific proof comes in later phases."""

    async def verify(self, task: TaskRecord, result: AgentOutput) -> Verification:
        if result.trace_id != task.trace_id:
            return Verification(ok=False, reason="trace ID mismatch")
        if result.status != AgentStatus.COMPLETED or result.error:
            return Verification(ok=False, reason=result.error or "agent did not complete")
        try:
            encoded = json.dumps(result.payload, allow_nan=False)
        except (TypeError, ValueError):
            return Verification(ok=False, reason="agent output is not valid JSON")
        if len(encoded) > 1_000_000:
            return Verification(ok=False, reason="agent output exceeds size limit")
        return Verification(ok=True)
