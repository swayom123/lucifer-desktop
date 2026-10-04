"""Single command boundary: parse, validate, authorize, execute, audit."""

import threading
import time
from collections.abc import Callable
from datetime import UTC, datetime

from ai.llm import LLMError
from core.conversation import ConversationMemory
from core.intent_parser import parse
from core.models import Action, Approval, Result, State
from core.permissions import Permissions
from core.state_machine import StateMachine
from core.tool_registry import ToolRegistry
from database.db import Database
from services.action_logging import create_logger, log_action


class Assistant:
    def __init__(self, registry: ToolRegistry, database: Database, planner=None):
        self.registry = registry
        self.database = database
        self.permissions = Permissions()
        self.lifecycle = StateMachine()
        self.logger = create_logger(database.path.parent)
        self._lock = threading.Lock()
        self.planner = planner
        self._continuations = {}
        self.conversation = ConversationMemory()
        self.conversation_mode = False

    def set_conversation_mode(self, active: bool) -> None:
        self.conversation_mode = bool(active)
        self.conversation.configure(
            max_turns=40 if active else 8,
            ttl_seconds=7200 if active else 300,
            max_chars=18000 if active else 6000,
        )

    def submit(
        self, command: str, emit: Callable[[State], None] = lambda _: None
    ) -> Result | Approval:
        return self._run(command=command, emit=emit)

    def confirm(
        self, token: str, emit: Callable[[State], None] = lambda _: None
    ) -> Result | Approval:
        return self._run(token=token, emit=emit)

    def decline(self, approval: Approval) -> Result:
        self.permissions.cancel(approval.token)
        self._continuations.pop(approval.token, None)
        result = Result(False, "CANCELLED", "Action cancelled. Remaining steps were not executed.")
        self.conversation.add("assistant", result.message)
        self._record(approval.action, result, time.monotonic())
        return result

    def _run(
        self,
        command: str = "",
        token: str | None = None,
        emit: Callable[[State], None] = lambda _: None,
    ) -> Result | Approval:
        if not self._lock.acquire(blocking=False):
            return Result(False, "BUSY", "Please wait for the current action to finish.")
        start = time.monotonic()
        action = None
        result = Result(False, "ACTION_FAILED", "The request did not finish.")
        recorded = False
        try:
            self.lifecycle.transition(State.THINKING)
            emit(State.THINKING)
            if token:
                remaining, messages = self._continuations.pop(token, ([], []))
                actions = [self.permissions.consume(token), *remaining]
            else:
                for pending_token in self._continuations:
                    self.permissions.cancel(pending_token)
                self._continuations.clear()
                if not isinstance(command, str) or not command.strip() or len(command) > 2000:
                    raise ValueError("Enter a command of 1–2000 characters.")
                if self.planner is not None:
                    context = self.conversation.context()
                    self.conversation.add("user", command)
                    # Exact local commands need no network round trip. Keep ambiguous
                    # requests and conversational follow-ups with the AI planner.
                    try:
                        local_action = parse(command)
                        self.registry.resolve(local_action)
                    except ValueError:
                        local_action = None
                    if local_action and (
                        local_action.tool == "open_application"
                        and local_action.arguments["app_name"].casefold()
                        not in {"it", "that", "this", "the app", "the application"}
                        or local_action.tool
                        in {
                            "next_video",
                            "seek_video",
                            "take_screenshot",
                            "system_info",
                            "list_applications",
                            "web_search",
                            "youtube_search",
                            "open_url",
                            "open_folder",
                            "create_folder",
                            "generate_program",
                        }
                    ):
                        actions = [local_action]
                    else:
                        if self.conversation_mode:
                            actions = self.planner.plan(
                                command,
                                self.registry,
                                context=context,
                                conversation_mode=True,
                            )
                        else:
                            actions = self.planner.plan(command, self.registry, context=context)
                else:
                    action = parse(command)
                    self.registry.resolve(action)
                    actions = [action]
                messages = []
            if isinstance(actions, Result):
                result = actions
                action = None
                self.conversation.add("assistant", result.message)
            else:
                for index, action in enumerate(actions):
                    recorded = False
                    tool, arguments = self.registry.resolve(action)
                    if not (token and index == 0):
                        level = tool.permission(arguments) if tool.permission else tool.level
                        approval = self.permissions.request(action, level, tool.description)
                        if approval:
                            self._continuations[approval.token] = (actions[index + 1 :], messages)
                            self._record(action, Result(False, "AWAITING_CONFIRMATION", ""), start)
                            self.conversation.add(
                                "assistant", f"Please confirm: {tool.description}."
                            )
                            self.lifecycle.transition(State.IDLE)
                            emit(State.IDLE)
                            return approval
                    if self.lifecycle.state != State.EXECUTING:
                        self.lifecycle.transition(State.EXECUTING)
                        emit(State.EXECUTING)
                    result = self.registry.execute(action)
                    self._record(action, result, start)
                    recorded = True
                    messages.append(result.message)
                    if not result.ok:
                        break
                if len(messages) > 1:
                    result = Result(result.ok, result.code, "\n\n".join(messages), result.data)
                self.conversation.add("assistant", result.message)
        except LLMError as error:
            result = Result(False, "MODEL_UNAVAILABLE", str(error))
        except ValueError as error:
            result = Result(False, "INVALID_REQUEST", str(error))
        except Exception:  # noqa: BLE001 — isolate adapter failures without leaking secrets
            # Tool adapters handle expected errors. Never surface unknown exception payloads.
            result = Result(
                False,
                "ACTION_FAILED",
                "The action failed. Check desktop permissions "
                "and try again; no success was recorded.",
            )
        finally:
            if self.lifecycle.state in {State.THINKING, State.EXECUTING}:
                self.lifecycle.transition(State.IDLE if result.ok else State.ERROR)
            self._lock.release()
        if not recorded:
            self._record(action, result, start)
        emit(State.IDLE if result.ok else State.ERROR)
        return result

    def _record(self, action: Action | None, result: Result, start: float) -> None:
        tool = action.tool if action else "unrecognized"
        record = {
            "time": datetime.now(UTC).isoformat(),
            "command": tool.replace("_", " "),
            "tool": tool,
            "code": result.code,
            "ok": result.ok,
            "duration_ms": round((time.monotonic() - start) * 1000),
        }
        self.database.record(record)
        log_action(self.logger, record)
