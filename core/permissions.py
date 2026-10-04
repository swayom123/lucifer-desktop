"""Expiring, single-use confirmations bound to validated immutable actions."""

import secrets
import threading
import time
from dataclasses import dataclass

from core.models import Action, Approval, Level


@dataclass(frozen=True)
class Pending:
    approval: Approval
    expires: float


class Permissions:
    def __init__(self, ttl: float = 120):
        self.ttl = ttl
        self._pending: dict[str, Pending] = {}
        self._lock = threading.Lock()

    def request(self, action: Action, level: Level, description: str) -> Approval | None:
        if level == Level.SAFE:
            return None
        with self._lock:
            now = time.monotonic()
            self._pending = {k: v for k, v in self._pending.items() if v.expires > now}
            approval = Approval(secrets.token_urlsafe(32), action, level, description)
            self._pending[approval.token] = Pending(approval, now + self.ttl)
            return approval

    def consume(self, token: str) -> Action:
        with self._lock:
            pending = self._pending.pop(token, None)
        if pending is None or pending.expires <= time.monotonic():
            raise ValueError("Confirmation expired or was already used. Submit the command again.")
        return pending.approval.action

    def cancel(self, token: str) -> None:
        with self._lock:
            self._pending.pop(token, None)
