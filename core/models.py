"""Immutable data crossing the planner, permission and executor boundaries."""

import json
from dataclasses import dataclass, field
from enum import IntEnum, StrEnum
from typing import Any


class State(StrEnum):
    IDLE = "IDLE"
    LISTENING = "LISTENING"
    THINKING = "THINKING"
    EXECUTING = "EXECUTING"
    SPEAKING = "SPEAKING"
    ERROR = "ERROR"


class Level(IntEnum):
    SAFE = 1
    CONFIRM = 2
    SENSITIVE = 3


@dataclass(frozen=True)
class Action:
    tool: str
    payload: str = "{}"

    @classmethod
    def create(cls, tool: str, **arguments: Any) -> "Action":
        return cls(tool, json.dumps(arguments, sort_keys=True))

    @property
    def arguments(self) -> dict[str, Any]:
        value = json.loads(self.payload)
        if not isinstance(value, dict):
            raise ValueError("Arguments must be an object.")  # noqa: TRY004 — validation contract
        return value


@dataclass(frozen=True)
class Result:
    ok: bool
    code: str
    message: str
    data: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Approval:
    token: str
    action: Action
    level: Level
    description: str
