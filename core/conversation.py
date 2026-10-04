"""Bounded, session-only context for resolving conversational follow-ups."""

import threading
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True)
class Turn:
    role: str
    content: str
    created: float


class ConversationMemory:
    """Keep a small recent transcript in RAM; never persist it to history or logs."""

    def __init__(
        self,
        max_turns: int = 8,
        ttl_seconds: float = 300,
        max_chars: int = 6000,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.max_turns = max_turns
        self.ttl_seconds = ttl_seconds
        self.max_chars = max_chars
        self._clock = clock
        self._turns: deque[Turn] = deque()
        self._lock = threading.Lock()

    def add(self, role: str, content: str) -> None:
        if role not in {"user", "assistant"} or not isinstance(content, str):
            return
        content = content.strip()
        if not content:
            return
        with self._lock:
            self._prune(self._clock())
            self._turns.append(Turn(role, content[:4000], self._clock()))
            self._trim()

    def configure(self, *, max_turns: int, ttl_seconds: float, max_chars: int) -> None:
        """Change the in-memory context window without persisting its contents."""
        with self._lock:
            self.max_turns = max(2, max_turns)
            self.ttl_seconds = max(1, ttl_seconds)
            self.max_chars = max(1000, max_chars)
            self._prune(self._clock())
            self._trim()

    @property
    def turn_count(self) -> int:
        with self._lock:
            self._prune(self._clock())
            return len(self._turns)

    def context(self) -> list[dict[str, str]]:
        with self._lock:
            self._prune(self._clock())
            selected = []
            size = 0
            for turn in reversed(self._turns):
                if size + len(turn.content) > self.max_chars:
                    break
                selected.append({"role": turn.role, "content": turn.content})
                size += len(turn.content)
            return list(reversed(selected))

    def clear(self) -> None:
        with self._lock:
            self._turns.clear()

    def _prune(self, now: float) -> None:
        while self._turns and now - self._turns[0].created > self.ttl_seconds:
            self._turns.popleft()

    def _trim(self) -> None:
        while len(self._turns) > self.max_turns:
            self._turns.popleft()
        while self._turns and sum(len(turn.content) for turn in self._turns) > self.max_chars:
            self._turns.popleft()
