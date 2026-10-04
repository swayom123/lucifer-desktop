"""Only registered, strictly validated actions can reach desktop adapters."""

from collections.abc import Callable
from dataclasses import dataclass

from core.models import Action, Level, Result


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    schema: dict[str, type]
    level: Level
    handler: Callable[..., Result]
    validator: Callable[[dict], None] | None = None
    permission: Callable[[dict], Level] | None = None

    def validate(self, arguments: dict) -> None:
        if set(arguments) != set(self.schema):
            raise ValueError("Invalid tool argument names.")
        for name, expected in self.schema.items():
            value = arguments[name]
            if type(value) is not expected:
                raise ValueError(f"{name} must be {expected.__name__}.")
            if isinstance(value, str) and (
                not value.strip() or len(value) > 2000 or any(ord(c) < 32 for c in value)
            ):
                raise ValueError(f"{name} must contain 1–2000 printable characters.")
        if self.validator:
            self.validator(arguments)


class ToolRegistry:
    def __init__(self):
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        if tool.name in self._tools:
            raise ValueError("Duplicate tool name.")
        self._tools[tool.name] = tool

    def resolve(self, action: Action) -> tuple[Tool, dict]:
        if action.tool not in self._tools:
            raise ValueError("This action is not available.")
        tool = self._tools[action.tool]
        arguments = action.arguments
        tool.validate(arguments)
        return tool, arguments

    def definitions(self) -> tuple[Tool, ...]:
        return tuple(self._tools.values())

    def execute(self, action: Action) -> Result:
        """Internal executor; application entrypoints use Assistant for authorization."""
        tool, arguments = self.resolve(action)
        return tool.handler(**arguments)
