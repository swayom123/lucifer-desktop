from types import SimpleNamespace

import pytest

from core.models import Result
from tools import answers, react_app
from tools.answers import Answers
from tools.media_worker import control_media, skip_ad
from tools.react_app import ReactWorkflow, validate_source


def test_answers_refine_search_and_only_cite_retrieved_sources(monkeypatch):
    searches = []

    def search(query):
        searches.append(query)
        return [{"title": "Source", "url": "https://example.com/facts", "snippet": "Evidence"}]

    monkeypatch.setattr(answers, "search_evidence", search)
    responses = iter(
        [{"search_query": "more recent facts"}, {"answer": "Supported fact.", "sources": [1]}]
    )
    client = SimpleNamespace(complete_json=lambda _: next(responses))
    result = Answers(client).answer_question("a current question")
    assert result.ok
    assert searches == ["a current question", "more recent facts"]
    assert result.data["spoken"] == "Supported fact."
    assert "https://example.com/facts" in result.message


def test_answer_rejects_fabricated_source_indices(monkeypatch):
    monkeypatch.setattr(
        answers, "search_evidence", lambda _: [{"title": "Source", "url": "https://example.com"}]
    )
    client = SimpleNamespace(complete_json=lambda _: {"answer": "Invented.", "sources": [99]})
    assert not Answers(client).answer_question("question").ok


@pytest.mark.parametrize(
    "code,css",
    [
        ('import secret from "../../.env?raw";', ""),
        ('import /* trick */ secret from "../../.env?raw";', ""),
        ('import("node:fs")', ""),
        ('new /* trick */ URL("../../.env", import.meta.url)', ""),
        ("export default function App() {}", '@import "https://example.com/style.css";'),
    ],
)
def test_react_rejects_external_build_inputs(code, css):
    with pytest.raises(ValueError):
        validate_source(code, css)


def test_react_repairs_build_and_runtime_errors(tmp_path, monkeypatch):
    monkeypatch.setattr(react_app, "WORKSPACE", tmp_path)
    monkeypatch.setattr(react_app.shutil, "which", lambda name: "/usr/bin/" + name)
    commands = []

    def run(command, **kwargs):
        commands.append(command)
        # First build fails, subsequent builds pass.
        return SimpleNamespace(returncode=int(len(commands) == 2), stdout="", stderr="syntax error")

    monkeypatch.setattr(react_app.subprocess, "run", run)
    prompts = []

    def generate(prompt):
        prompts.append(prompt)
        return {
            "code": "import React from 'react'; export default function App(){return <h1>Form</h1>}",
            "css": "body {color: black}",
            "summary": "Form",
        }

    opened = []
    workflow = ReactWorkflow(
        SimpleNamespace(complete_json=generate), SimpleNamespace(_open_project=opened.append)
    )
    checks = iter(["runtime error", ""])
    monkeypatch.setattr(workflow, "_check_preview", lambda url: next(checks))
    monkeypatch.setattr("tools.browser.open_url", lambda url: Result(True, "OPENED", "Opened"))
    try:
        result = workflow.create_react_app("a student form")
        assert result.ok
        assert result.data["attempts"] == 3
        assert "syntax error" in prompts[1]
        assert "runtime error" in prompts[2]
        assert len(opened) == 1
        assert "--ignore-scripts" in commands[0]
        assert (opened[0] / "App.jsx").is_file()
    finally:
        workflow.close()


def test_skip_ads_only_clicks_available_button():
    clicks = []
    button = SimpleNamespace(
        is_visible=lambda: True, is_enabled=lambda: True, click=lambda **kwargs: clicks.append(True)
    )
    page = SimpleNamespace(locator=lambda _: SimpleNamespace(first=button))
    assert skip_ad(page)
    assert clicks == [True]
    button.is_visible = lambda: False
    assert not skip_ad(page)
    assert clicks == [True]


def test_control_media_seeks_html5_video():
    class Video:
        def is_visible(self):
            return True

        def evaluate(self, _script, seconds):
            assert seconds == 30
            return 90

    page = SimpleNamespace(locator=lambda _: SimpleNamespace(first=Video()))
    result = control_media(page, "seek", 30)
    assert result["code"] == "VIDEO_SEEKED"


def test_control_media_clicks_next_button():
    clicks = []

    class Button:
        def is_visible(self):
            return True

        def is_enabled(self):
            return True

        def click(self, **_):
            clicks.append(True)

    class Page:
        def locator(self, _):
            return SimpleNamespace(first=Button())

    result = control_media(Page(), "next")
    assert result["code"] == "NEXT_VIDEO"
    assert clicks == [True]
