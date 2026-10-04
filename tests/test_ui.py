from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMessageBox

from config.settings import Settings
from core.bootstrap import build
from core.models import Level, Result
from core.tool_registry import Tool
from ui.main_window import MainWindow


def make_window(qtbot, tmp_path):
    settings = Settings(tmp_path)
    assistant, apps = build(settings)
    window = MainWindow(assistant, apps, settings)
    qtbot.addWidget(window)
    window.show()
    return window


def test_typed_command_history_and_feedback(qtbot, tmp_path):
    window = make_window(qtbot, tmp_path)
    calls = []
    window.assistant.registry._tools["open_application"] = Tool(
        "open_application",
        "Open application",
        {"app_name": str},
        Level.SAFE,
        lambda **kw: calls.append(kw) or Result(True, "LAUNCH_REQUESTED", "Launch requested."),
    )
    window.input.setText("Open VS Code")
    qtbot.keyClick(window.input, Qt.Key.Key_Return)
    qtbot.waitUntil(lambda: not window.busy)
    assert calls == [{"app_name": "VS Code"}]
    assert window.response.text() == "Launch requested."
    assert window.history.rowCount() == 1
    assert "SUCCESS" in window.state_label.text()
    qtbot.waitUntil(lambda: "IDLE" in window.state_label.text(), timeout=2000)


def test_ui_confirmation_cancel_has_no_effect(qtbot, tmp_path):
    window = make_window(qtbot, tmp_path)
    window.input.setText("Create a folder called Lucifer test folder")
    window.submit()
    qtbot.waitUntil(lambda: window.dialog is not None)
    assert window.busy
    window.dialog.button(QMessageBox.StandardButton.Cancel).click()
    qtbot.waitUntil(lambda: not window.busy)
    assert "cancelled" in window.response.text()
    assert window.assistant.database.recent()[0]["code"] == "CANCELLED"


def test_unsupported_request_and_navigation(qtbot, tmp_path):
    window = make_window(qtbot, tmp_path)
    window.input.setText("sudo rm -rf /")
    window.submit()
    qtbot.waitUntil(lambda: not window.busy)
    assert "not supported" in window.response.text()
    expected = {0: 0, 1: 0, 2: 2, 4: 1, 5: 7, 6: 9}
    for index, page in expected.items():
        window.navigation.setCurrentRow(index)
        assert window.pages.currentIndex() == page
    assert window.application_table.rowCount() >= 8


def test_startup_briefing_shown_and_sent_to_voice(qtbot, tmp_path, monkeypatch):
    window = make_window(qtbot, tmp_path)
    spoken = []
    monkeypatch.setattr(window.speech, "speak", spoken.append)
    window.show_startup_briefing()
    qtbot.waitUntil(lambda: not window.busy)
    assert "Lucifer is ready" in window.response.text()
    assert spoken == [window.response.text()]
    assert window.command_label.text() == "Your login briefing"


def test_voice_command_executes_and_speaks(qtbot, tmp_path, monkeypatch):
    window = make_window(qtbot, tmp_path)
    calls = []
    spoken = []
    monkeypatch.setattr(window.speech, "speak", spoken.append)
    window.assistant.registry._tools["open_application"] = Tool(
        "open_application",
        "Open application",
        {"app_name": str},
        Level.SAFE,
        lambda **kw: calls.append(kw) or Result(True, "LAUNCH_REQUESTED", "Opening VS Code."),
    )
    window.voice_controls.recognized.emit("Open VS Code")
    qtbot.waitUntil(lambda: not window.busy)
    assert calls == [{"app_name": "VS Code"}]
    assert spoken == ["Opening VS Code."]
    assert not window.voice_reply_pending


def test_wake_word_prompts_for_follow_up_command(qtbot, tmp_path, monkeypatch):
    window = make_window(qtbot, tmp_path)
    spoken = []
    monkeypatch.setattr(window.speech, "speak", spoken.append)

    window._wake_detected()

    assert spoken == ["Yes, how can I help?"]


def test_voice_clarification_keeps_listener_ready_for_answer(qtbot, tmp_path, monkeypatch):
    window = make_window(qtbot, tmp_path)
    spoken = []
    monkeypatch.setattr(window.speech, "speak", spoken.append)
    window.wake_listener.running = True
    window.voice_reply_pending = True

    window._finished(Result(True, "AI_CLARIFICATION", "What would you like to play next?"))

    assert spoken == ["What would you like to play next?"]
    assert window.wake_listener.awaiting_command
    assert not window.voice_reply_pending


def test_voice_paths_reuse_one_model(qtbot, tmp_path):
    window = make_window(qtbot, tmp_path)
    assert window.wake_listener.stt is window.voice_controls.stt
    assert window.wake_listener.pool is window.voice_controls.pool
    assert window.pool.maxThreadCount() == 1


def test_window_uses_configured_wake_word(qtbot, tmp_path):
    settings = Settings(tmp_path, wake_word="computer")
    assistant, apps = build(settings)
    window = MainWindow(assistant, apps, settings)
    qtbot.addWidget(window)

    assert window.wake_listener.wake_word == "computer"


def test_voice_confirmation_still_requires_click(qtbot, tmp_path, monkeypatch):
    window = make_window(qtbot, tmp_path)
    spoken = []
    monkeypatch.setattr(window.speech, "speak", spoken.append)
    window.voice_controls.recognized.emit("Create a folder called Voice Test")
    qtbot.waitUntil(lambda: window.dialog is not None)
    assert window.assistant.database.recent()[0]["code"] == "AWAITING_CONFIRMATION"
    window.dialog.button(QMessageBox.StandardButton.Cancel).click()
    qtbot.waitUntil(lambda: not window.busy)
    assert window.assistant.database.recent()[0]["code"] == "CANCELLED"
    assert "cancelled" in spoken[-1]


def test_cancelled_voice_result_never_submits(qtbot, tmp_path):
    window = make_window(qtbot, tmp_path)
    recognized = []
    window.voice_controls.recognized.connect(recognized.append)
    window.voice_controls.active = True
    window.voice_controls.transcribing = True
    window.voice_controls.cancel_capture()
    window.voice_controls._result(Result(True, "VOICE_TRANSCRIPT", "Open VS Code"))
    assert recognized == []
    assert window.assistant.database.recent() == []


def test_compact_navigation_and_long_response_remain_usable(qtbot, tmp_path):
    from ui.theme import STYLESHEET

    window = make_window(qtbot, tmp_path)
    window.setStyleSheet(STYLESHEET)
    window.resize(390, 720)
    qtbot.wait(30)
    assert window.mobile_nav.isVisible()
    assert not window.side_widget.isVisible()
    assert not window.action_panel.isVisible()
    window.mobile_nav.activated.emit(6)
    assert window.pages.currentIndex() == 9
    window.mobile_nav.activated.emit(0)
    window._finished(Result(True, "ANSWER", "A long answer with useful details. " * 150))
    qtbot.wait(30)
    assert window.feedback.verticalScrollBar().maximum() > 0
    assert window.pages.widget(0).horizontalScrollBar().maximum() == 0
    assert window.input.isVisible()
    assert window.input.width() > 160


def test_composer_respects_voice_availability_and_empty_input(qtbot, tmp_path):
    window = make_window(qtbot, tmp_path)
    assert not window.send.isEnabled()
    window.input.setText("System status")
    assert window.send.isEnabled()
    window.voice_controls.set_hands_free(True)
    assert not window.mic_button.isEnabled()
    window.voice_controls.set_hands_free(False)
    assert window.mic_button.isEnabled()
    window.voice_controls.set_speaking(True)
    assert not window.mic_button.isEnabled()
    window.voice_controls.set_speaking(False)
    window.input.clear()
    assert not window.send.isEnabled()


def test_action_card_supports_enter_and_focuses_command(qtbot, tmp_path):
    window = make_window(qtbot, tmp_path)
    card = window.action_panel.cards[1]
    card.setFocus()
    qtbot.keyClick(card, Qt.Key.Key_Return)
    assert window.input.text() == "Search Google for "
    assert window.focusWidget() is window.input
