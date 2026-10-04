import json
from urllib.parse import parse_qs, urlsplit

import pytest

from automation.application_registry import ApplicationRegistry
from automation.platforms import detect_os
from core.assistant import Assistant
from core.intent_parser import parse
from core.models import Action, Approval, Level, Result, State
from core.permissions import Permissions
from core.tool_registry import Tool, ToolRegistry
from database.db import Database
from tools.browser import search_url, validate_url
from tools.files import validate_folder_name, validate_path


@pytest.mark.parametrize(
    "text,tool,args",
    [
        ("Open VS Code", "open_application", {"app_name": "VS Code"}),
        ("Hey Lucifer, Open VS Code.", "open_application", {"app_name": "VS Code"}),
        ("Search Google for Python decorators.", "web_search", {"query": "Python decorators"}),
        ("Search YouTube for Python tutorials", "youtube_search", {"query": "Python tutorials"}),
        ("Play the next video", "next_video", {}),
        ("Skip 30 seconds", "seek_video", {"seconds": 30}),
        ("Go back 5 minutes", "seek_video", {"seconds": -300}),
        ("Take a screenshot.", "take_screenshot", {}),
        ("Open my Downloads folder", "open_folder", {"name": "downloads"}),
        ("Create a folder called AI Projects", "create_folder", {"name": "AI Projects"}),
        ("Open GitHub", "open_url", {"url": "https://github.com"}),
        ("Lucifer open GitHub", "open_url", {"url": "https://github.com"}),
        ("List installed applications", "list_applications", {}),
    ],
)
def test_parser(text, tool, args):
    action = parse(text)
    assert action.tool == tool
    assert action.arguments == args


@pytest.mark.parametrize("command", ["", "rm -rf /", "sudo reboot", "format disk", "x" * 2001])
def test_parser_rejects_unknown(command):
    with pytest.raises(ValueError):
        parse(command)


def test_registry_rejects_unknown_arguments_types_and_duplicates():
    registry = ToolRegistry()
    tool = Tool("test", "test", {"name": str}, Level.SAFE, lambda **kw: Result(True, "OK", ""))
    registry.register(tool)
    for action in [
        Action.create("missing"),
        Action.create("test", name=True),
        Action.create("test", name="ok", shell="bad"),
        Action.create("test", name="\n"),
    ]:
        with pytest.raises(ValueError):
            registry.resolve(action)
    with pytest.raises(ValueError):
        registry.register(tool)


@pytest.mark.parametrize("level", [Level.CONFIRM, Level.SENSITIVE])
def test_permission_gate_and_single_use(level):
    permissions = Permissions()
    action = Action.create("test", value="original")
    approval = permissions.request(action, level, "Review")
    assert approval is not None
    mutated = approval.action.arguments
    mutated["value"] = "tampered"
    assert permissions.consume(approval.token).arguments == {"value": "original"}
    with pytest.raises(ValueError):
        permissions.consume(approval.token)


def test_safe_cancel_expire_and_forgery():
    permissions = Permissions(ttl=-1)
    action = Action.create("test")
    assert permissions.request(action, Level.SAFE, "") is None
    approval = permissions.request(action, Level.SENSITIVE, "")
    with pytest.raises(ValueError):
        permissions.consume(approval.token)
    permissions = Permissions()
    approval = permissions.request(action, Level.CONFIRM, "")
    permissions.cancel(approval.token)
    for token in (approval.token, "forged"):
        with pytest.raises(ValueError):
            permissions.consume(token)


def make_assistant(tmp_path, level=Level.SAFE):
    calls = []
    registry = ToolRegistry()
    registry.register(
        Tool(
            "open_application",
            "Open application",
            {"app_name": str},
            level,
            lambda **kw: calls.append(kw) or Result(True, "LAUNCH_REQUESTED", "Done"),
        )
    )
    return Assistant(registry, Database(tmp_path / "history.db")), calls


def test_confirmation_prevents_execution_and_audits(tmp_path):
    assistant, calls = make_assistant(tmp_path, Level.SENSITIVE)
    approval = assistant.submit("Open VS Code")
    assert isinstance(approval, Approval)
    assert calls == []
    result = assistant.confirm(approval.token)
    assert result.ok and len(calls) == 1
    assert not assistant.confirm(approval.token).ok
    assert len(calls) == 1
    assert assistant.database.recent()[0]["code"] == "INVALID_REQUEST"


def test_declining_does_not_execute(tmp_path):
    assistant, calls = make_assistant(tmp_path, Level.CONFIRM)
    approval = assistant.submit("Open VS Code")
    assert assistant.decline(approval).code == "CANCELLED"
    assert not assistant.confirm(approval.token).ok
    assert calls == []


def test_state_history_and_secret_privacy(tmp_path):
    assistant, _calls = make_assistant(tmp_path)
    states = []
    secret = "password=very-secret-value"
    assert assistant.submit(f"Open {secret}", states.append).ok
    assert states == [State.THINKING, State.EXECUTING, State.IDLE]
    assert secret not in json.dumps(assistant.database.recent())
    assert secret not in (tmp_path / "actions.jsonl").read_text()
    assert assistant.database.recent()[0]["tool"] == "open_application"


def test_unexpected_tool_error_does_not_leak(tmp_path):
    assistant, _ = make_assistant(tmp_path)

    def fail(**kw):
        raise RuntimeError("secret-key=do-not-persist")

    assistant.registry._tools["open_application"] = Tool(
        "open_application", "", {"app_name": str}, Level.SAFE, fail
    )
    result = assistant.submit("Open VS Code")
    assert result.code == "ACTION_FAILED"
    assert "secret-key" not in result.message
    assert "secret-key" not in (tmp_path / "actions.jsonl").read_text()


@pytest.mark.parametrize("system", ["Linux", "Windows", "Darwin"])
def test_platform_detection(monkeypatch, system):
    monkeypatch.setattr("platform.system", lambda: system)
    assert detect_os() == system


def test_unsupported_platform(monkeypatch):
    monkeypatch.setattr("platform.system", lambda: "Unknown")
    with pytest.raises(RuntimeError):
        detect_os()


def test_discovery_aliases_and_launch_argv(monkeypatch):
    registry = ApplicationRegistry("Linux")
    app = registry.resolve("VS Code")
    assert app is registry.resolve("vscode") is registry.resolve("code")
    monkeypatch.setattr("shutil.which", lambda name: "/usr/bin/code" if name == "code" else None)
    assert registry.command(app) == ["/usr/bin/code"]
    commands = []

    class Process:
        def __init__(self, command, **kwargs):
            commands.append((command, kwargs))

        def wait(self, timeout):
            return 0

    monkeypatch.setattr("subprocess.Popen", Process)
    assert registry.launch("VS Code").ok
    assert commands[0][0] == ["/usr/bin/code"]
    assert not commands[0][1].get("shell", False)
    assert registry.level({"app_name": "terminal"}) == Level.CONFIRM
    with pytest.raises(ValueError):
        registry.launch("code; rm -rf /")


def test_missing_app_is_truthful(monkeypatch):
    registry = ApplicationRegistry("Linux")
    monkeypatch.setattr(registry, "command", lambda app: None)
    assert registry.launch("Spotify").code == "APP_NOT_INSTALLED"


def test_desktop_entry_discovery_is_shell_free(tmp_path, monkeypatch):
    applications = tmp_path / "applications"
    applications.mkdir()
    (applications / "safe.desktop").write_text(
        "[Desktop Entry]\nType=Application\nName=Safe Editor\nExec=/usr/bin/code --reuse-window\n"
    )
    (applications / "unsafe.desktop").write_text(
        '[Desktop Entry]\nType=Application\nName=Unsafe Launcher\nExec=sh -c "rm -rf /"\n'
    )
    monkeypatch.setenv("XDG_DATA_DIRS", str(tmp_path))
    monkeypatch.setattr("shutil.which", lambda name: "/usr/bin/" + name if name == "code" else None)
    registry = ApplicationRegistry("Linux")
    assert registry.resolve("safe editor").desktop_command == ("/usr/bin/code", "--reuse-window")
    with pytest.raises(ValueError):
        registry.resolve("unsafe launcher")


def test_desktop_entry_rejects_shell_metacharacters():
    assert ApplicationRegistry._desktop_exec("code; rm -rf /") == ()


def test_parser_accepts_spoken_wake_prefix():
    assert parse("Lucifer open VS Code").arguments == {"app_name": "VS Code"}


@pytest.mark.parametrize("youtube", [False, True])
def test_search_encoding(youtube):
    query = "C++ decorators & privacy # α"
    parsed = urlsplit(search_url(query, youtube))
    assert parsed.scheme == "https"
    assert parse_qs(parsed.query)["search_query" if youtube else "q"] == [query]


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "javascript:alert(1)",
        "https://user:pass@a.com",
        "https://example.com:bad",
        "https://",
        "https://a.com\nfoo",
        "https://a.com\\b",
    ],
)
def test_url_rejects_unsafe_schemes_and_credentials(url):
    with pytest.raises(ValueError):
        validate_url(url)


def test_path_rejects_escape_hidden_and_symlink(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    assert validate_path(home / "Documents", home) == home / "Documents"
    (home / "escape").symlink_to(tmp_path, target_is_directory=True)
    for path in (home / "../secret", home / ".ssh/id_rsa", home / "escape/secret"):
        with pytest.raises(ValueError):
            validate_path(path, home)


@pytest.mark.parametrize("name", ["../escape", "/root", ".ssh", "a/b", "a\\b", "NUL", "CON.txt"])
def test_folder_name_rejects_paths(name):
    with pytest.raises(ValueError):
        validate_folder_name(name)


def test_browser_reports_failure(monkeypatch):
    from tools.browser import web_search

    monkeypatch.setattr("webbrowser.open", lambda *args, **kw: False)
    assert not web_search("test").ok


def test_screenshot_denial(monkeypatch, tmp_path):
    from tools import screenshots

    monkeypatch.setenv("WAYLAND_DISPLAY", "test")

    async def denied():
        raise PermissionError()

    monkeypatch.setattr(screenshots, "portal_screenshot", denied)
    result = screenshots.take_screenshot(tmp_path)
    assert result.code == "SCREENSHOT_DENIED"
    assert not list(tmp_path.glob("*.png"))


def test_state_machine_rejects_impossible_transitions():
    from core.state_machine import StateMachine

    machine = StateMachine()
    with pytest.raises(ValueError):
        machine.transition(State.EXECUTING)
    for state in (State.LISTENING, State.THINKING, State.EXECUTING, State.SPEAKING, State.IDLE):
        machine.transition(state)
    assert machine.state == State.IDLE


def test_lifecycle_after_confirmation_and_failure(tmp_path):
    assistant, _ = make_assistant(tmp_path, Level.CONFIRM)
    approval = assistant.submit("Open VS Code")
    assert assistant.lifecycle.state == State.IDLE
    assert assistant.confirm(approval.token).ok
    assert assistant.lifecycle.state == State.IDLE
    assert not assistant.submit("unsupported").ok
    assert assistant.lifecycle.state == State.ERROR
    assert isinstance(assistant.submit("Open VS Code"), Approval)
    assert assistant.lifecycle.state == State.IDLE


def test_exact_local_command_skips_ai_planning(tmp_path):
    assistant, calls = make_assistant(tmp_path)

    class Planner:
        def plan(self, *args, **kwargs):
            raise AssertionError("Exact local commands should not call the AI provider")

    assistant.planner = Planner()
    assert assistant.submit("Open VS Code").ok
    assert calls == [{"app_name": "VS Code"}]


def test_ambiguous_command_uses_ai_planning(tmp_path):
    assistant, calls = make_assistant(tmp_path)

    class Planner:
        def __init__(self):
            self.requests = []

        def plan(self, request, registry, context=None):
            self.requests.append(request)
            return [Action.create("open_application", app_name="VS Code")]

    assistant.planner = Planner()
    assert assistant.submit("Could you open my editor?").ok
    assert assistant.planner.requests == ["Could you open my editor?"]
    assert calls == [{"app_name": "VS Code"}]
