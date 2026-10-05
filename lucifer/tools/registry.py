"""Validated tool metadata registry; execution is intentionally a separate boundary."""

from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field

from lucifer.core.tasks import RiskLevel


class ToolDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    description: str
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    permissions: frozenset[str] = frozenset()
    risk_level: RiskLevel
    timeout_seconds: float = Field(gt=0)


class Tool(Protocol):
    @property
    def definition(self) -> ToolDefinition: ...


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        name = tool.definition.name
        if name in self._tools:
            raise ValueError(f"duplicate tool: {name}")
        self._tools[name] = tool

    def get(self, name: str) -> Tool:
        return self._tools[name]

    def definitions(self) -> tuple[ToolDefinition, ...]:
        return tuple(tool.definition for tool in self._tools.values())
