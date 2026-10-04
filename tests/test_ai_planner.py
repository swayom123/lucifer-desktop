import pytest

from ai.llm import LLMError
from ai.planner import Planner
from core.assistant import Assistant
from core.conversation import ConversationMemory
from core.models import Approval, Level, Result
from core.tool_registry import Tool, ToolRegistry
from database.db import Database


class Client:
    def __init__(self, response):
        self.response = response

    def complete_json(self, prompt):
        return self.response


class SequenceClient:
    def __init__(self, *responses):
        self.responses = iter(responses)
        self.prompts = []

    def complete_json(self, prompt):
        self.prompts.append(prompt)
        return next(self.responses)


def make_assistant(tmp_path, plan, fail=False):
    calls = []
    registry = ToolRegistry()
    for name, level in (("first", Level.SAFE), ("second", Level.CONFIRM), ("third", Level.CONFIRM)):

        def handler(name=name):
            calls.append(name)
            return Result(not (fail and name == "first"), "DONE", name)

        registry.register(Tool(name, name, {}, level, handler))
    return Assistant(registry, Database(tmp_path / "ai.db"), Planner(Client(plan))), calls


def plan(*names):
    return {"actions": [{"tool": name, "arguments": {}} for name in names]}


def test_each_step_is_confirmed_without_repeating_previous_steps(tmp_path):
    assistant, calls = make_assistant(tmp_path, plan("first", "second", "third"))
    approval = assistant.submit("please do the three tasks")
    assert calls == ["first"]
    assert isinstance(approval, Approval)
    next_approval = assistant.confirm(approval.token)
    assert isinstance(next_approval, Approval)
    assert calls == ["first", "second"]
    result = assistant.confirm(next_approval.token)
    assert result.ok
    assert result.message == "first\n\nsecond\n\nthird"
    assert calls == ["first", "second", "third"]
    assert not assistant.confirm(next_approval.token).ok
    assert len(calls) == 3


def test_decline_discards_remaining_plan(tmp_path):
    assistant, calls = make_assistant(tmp_path, plan("second", "third"))
    approval = assistant.submit("do both")
    assistant.decline(approval)
    assert not assistant.confirm(approval.token).ok
    assert not calls
    assert not assistant._continuations


def test_invalid_later_step_prevents_all_execution(tmp_path):
    assistant, calls = make_assistant(tmp_path, plan("first", "shell"))
    assert not assistant.submit("execute this").ok
    assert not calls


def test_failure_stops_remaining_steps_and_is_recorded_once(tmp_path):
    assistant, calls = make_assistant(tmp_path, plan("first", "second"), fail=True)
    assert not assistant.submit("do tasks").ok
    assert calls == ["first"]
    assert len(assistant.database.recent()) == 1


@pytest.mark.parametrize(
    "response",
    [
        plan(),
        plan(*(["first"] * 6)),
        {"actions": "shell"},
        {"actions": [{"tool": "first", "arguments": {"extra": "x"}}]},
    ],
)
def test_bad_ai_plans_never_execute(tmp_path, response):
    assistant, calls = make_assistant(tmp_path, response)
    assert not assistant.submit("do it").ok
    assert not calls


def test_clarification_is_displayed_without_executing(tmp_path):
    assistant, calls = make_assistant(tmp_path, {"reply": "Which application do you mean?"})
    assert assistant.submit("open that").code == "AI_CLARIFICATION"
    assert not calls


def test_clarification_follow_up_uses_short_term_context(tmp_path):
    played = []
    registry = ToolRegistry()
    registry.register(
        Tool(
            "play_youtube",
            "Play YouTube music",
            {"query": str},
            Level.SAFE,
            lambda query: played.append(query) or Result(True, "YOUTUBE_PLAYING", "Playing."),
        )
    )
    client = SequenceClient(
        {"reply": "Which songs would you like?"},
        {"actions": [{"tool": "play_youtube", "arguments": {"query": "Hindi songs"}}]},
    )
    assistant = Assistant(registry, Database(tmp_path / "conversation.db"), Planner(client))

    clarification = assistant.submit("Play songs")
    result = assistant.submit("Hindi songs")

    assert clarification.code == "AI_CLARIFICATION"
    assert result.ok
    assert played == ["Hindi songs"]
    assert '"content": "Play songs"' in client.prompts[1]
    assert '"content": "Which songs would you like?"' in client.prompts[1]
    persisted = (tmp_path / "actions.jsonl").read_text()
    assert "Play songs" not in persisted
    assert "Hindi songs" not in persisted


def test_conversation_memory_is_bounded_and_expires():
    now = [100.0]
    memory = ConversationMemory(max_turns=2, ttl_seconds=5, clock=lambda: now[0])
    memory.add("user", "first")
    memory.add("assistant", "second")
    memory.add("user", "third")

    assert [turn["content"] for turn in memory.context()] == ["second", "third"]

    now[0] += 6
    assert memory.context() == []


def test_follow_up_keeps_prior_music_time_constraint():
    registry = ToolRegistry()
    registry.register(
        Tool(
            "play_youtube",
            "Play YouTube music",
            {"query": str},
            Level.SAFE,
            lambda **_: Result(True, "OK", ""),
        )
    )
    planner = Planner(
        Client(
            {
                "actions": [
                    {
                        "tool": "play_youtube",
                        "arguments": {"query": "latest Hindi music September 2026"},
                    }
                ]
            }
        )
    )

    actions = planner.plan(
        "Hindi music",
        registry,
        context=[
            {"role": "user", "content": "Play latest songs"},
            {"role": "assistant", "content": "Which songs?"},
        ],
    )

    assert actions[0].arguments["query"] == "latest Hindi music September 2026"


def test_music_query_preserves_language_without_inventing_latest(tmp_path):
    registry = ToolRegistry()
    registry.register(
        Tool(
            "play_youtube",
            "Play YouTube music",
            {"query": str},
            Level.SAFE,
            lambda **_: Result(True, "OK", ""),
        )
    )
    planner = Planner(
        Client(
            {
                "actions": [
                    {"tool": "play_youtube", "arguments": {"query": "Hindi music September 2026"}}
                ]
            }
        )
    )

    actions = planner.plan("play Hindi music", registry)

    assert actions[0].arguments == {"query": "Hindi music"}


def test_music_query_keeps_explicit_latest_constraint(tmp_path):
    registry = ToolRegistry()
    registry.register(
        Tool(
            "play_youtube",
            "Play YouTube music",
            {"query": str},
            Level.SAFE,
            lambda **_: Result(True, "OK", ""),
        )
    )
    planner = Planner(
        Client(
            {
                "actions": [
                    {
                        "tool": "play_youtube",
                        "arguments": {"query": "latest Hindi music September 2026"},
                    }
                ]
            }
        )
    )

    actions = planner.plan("play latest Hindi music", registry)

    assert actions[0].arguments["query"] == "latest Hindi music September 2026"


def test_planner_uses_media_controls_for_current_video(tmp_path):
    registry = ToolRegistry()
    registry.register(
        Tool("next_video", "Play next", {}, Level.SAFE, lambda: Result(True, "OK", ""))
    )
    registry.register(
        Tool("seek_video", "Seek", {"seconds": int}, Level.SAFE, lambda **_: Result(True, "OK", ""))
    )
    planner = Planner(Client({"actions": [{"tool": "seek_video", "arguments": {"seconds": 30}}]}))

    actions = planner.plan("skip forward 30 seconds", registry)

    assert actions[0].tool == "seek_video"
    assert actions[0].arguments == {"seconds": 30}


def test_provider_failure_is_not_reported_as_success(tmp_path):
    assistant, calls = make_assistant(tmp_path, plan("first"))

    def unavailable(prompt):
        raise LLMError("Free-tier quota unavailable.")

    assistant.planner.client.complete_json = unavailable
    assert assistant.submit("anything").code == "MODEL_UNAVAILABLE"
    assert not calls
