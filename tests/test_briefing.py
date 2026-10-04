from datetime import UTC, datetime

from core.models import Result
from services.briefing import build_briefing
from voice.text_to_speech import LocalSpeech


def test_briefing_uses_measurements(monkeypatch):
    monkeypatch.setattr(
        "services.briefing.system_info",
        lambda: Result(
            True,
            "",
            "",
            {
                "battery_percent": 73,
                "ram_percent": 21,
                "disk_percent": 48,
                "network_interface_up": True,
            },
        ),
    )
    result = build_briefing(datetime(2026, 9, 21, 9, 30, tzinfo=UTC))
    assert result.code == "STARTUP_BRIEFING"
    for text in ("Good morning", "09:30 AM", "73 percent", "21 percent", "48 percent"):
        assert text in result.message


def test_briefing_no_battery_and_no_network(monkeypatch):
    monkeypatch.setattr(
        "services.briefing.system_info",
        lambda: Result(
            True,
            "",
            "",
            {
                "battery_percent": None,
                "ram_percent": 21,
                "disk_percent": 48,
                "network_interface_up": False,
            },
        ),
    )
    text = build_briefing(datetime(2026, 9, 21, 19, tzinfo=UTC)).message
    assert "Good evening" in text
    assert "battery" not in text
    assert "No active network interface" in text


def test_missing_voice_keeps_text(qtbot, monkeypatch):
    monkeypatch.delenv("LIVEKIT_API_KEY", raising=False)
    monkeypatch.delenv("LIVEKIT_API_SECRET", raising=False)
    monkeypatch.setattr("voice.text_to_speech.shutil.which", lambda _: None)
    speech = LocalSpeech()
    with qtbot.waitSignal(speech.status) as signal:
        speech.speak("Welcome")
    assert "shown on screen" in signal.args[0]


def test_livekit_requires_both_credentials(monkeypatch):
    monkeypatch.setenv("TTS_PROVIDER", "livekit")
    monkeypatch.setenv("LIVEKIT_API_KEY", "key")
    monkeypatch.delenv("LIVEKIT_API_SECRET", raising=False)
    assert not LocalSpeech._livekit_ready()

    monkeypatch.setenv("LIVEKIT_API_SECRET", "secret")
    assert LocalSpeech._livekit_ready()


def test_duplicate_startup_exits_silently(qtbot, tmp_path):
    import os
    import subprocess
    import sys
    from pathlib import Path

    from PySide6.QtCore import QLockFile

    lock = QLockFile(str(tmp_path / "lucifer.lock"))
    assert lock.tryLock(100)
    try:
        environment = dict(os.environ, LUCIFER_DATA_DIR=str(tmp_path), QT_QPA_PLATFORM="offscreen")
        result = subprocess.run(
            [sys.executable, str(Path(__file__).resolve().parents[1] / "main.py"), "--startup"],
            env=environment,
            timeout=10,
            capture_output=True,
            check=False,
        )
        assert result.returncode == 0
    finally:
        lock.unlock()
