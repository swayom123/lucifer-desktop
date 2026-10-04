"""Nonblocking LiveKit speech with a local Speech Dispatcher fallback."""

from __future__ import annotations

import os
import shutil
import sys

from PySide6.QtCore import QObject, QProcess, QTimer, Signal


class LocalSpeech(QObject):
    """Speak responses without blocking the UI or retaining generated audio."""

    status = Signal(str)
    active_changed = Signal(bool)
    level = Signal(int)

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self.pending: str | None = None
        self._current_text = ""
        self._provider = ""
        self._fallback_attempted = False
        self._level_buffer = b""
        self.process = QProcess(self)
        self.process.finished.connect(self._finished)
        self.process.errorOccurred.connect(self._failed)
        self.process.readyReadStandardOutput.connect(self._read_levels)
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self._timeout)

    @staticmethod
    def _livekit_ready() -> bool:
        return (
            os.getenv("TTS_PROVIDER", "livekit").lower() == "livekit"
            and bool(os.getenv("LIVEKIT_API_KEY"))
            and bool(os.getenv("LIVEKIT_API_SECRET"))
        )

    def speak(self, text: str) -> None:
        text = text.strip()
        if not text:
            return
        if self.process.state() != QProcess.ProcessState.NotRunning:
            self.pending = text
            return

        self._current_text = text
        self._level_buffer = b""
        self._fallback_attempted = False
        self.active_changed.emit(True)
        if self._livekit_ready():
            self._start_livekit(text)
        else:
            self._start_local(text)

    def _start_livekit(self, text: str) -> None:
        self._provider = "livekit"
        self.process.setProgram(sys.executable)
        self.process.setArguments(["-m", "voice.livekit_tts_worker"])
        self.process.start()
        self.process.write(text.encode("utf-8"))
        self.process.closeWriteChannel()
        self.timer.start(90000)
        self.status.emit("Speaking with LiveKit · Brandon…")

    def _start_local(self, text: str) -> bool:
        executable = shutil.which("spd-say")
        if not executable:
            self.active_changed.emit(False)
            self.status.emit("Voice is unavailable; the response is shown on screen.")
            self._play_pending()
            return False
        self._provider = "local"
        self.process.setProgram(executable)
        self.process.setArguments(["-w", "-N", "Lucifer", "-l", "en", "--", text])
        self.process.start()
        self.timer.start(60000)
        message = (
            "LiveKit voice failed; using the local voice."
            if self._fallback_attempted
            else "Reading the response with the local voice engine…"
        )
        self.status.emit(message)
        return True

    def _finished(self, code: int, _status: QProcess.ExitStatus) -> None:
        self.timer.stop()
        self.level.emit(0)
        if self._provider == "livekit" and code != 0 and not self._fallback_attempted:
            self._fallback_attempted = True
            if self._start_local(self._current_text):
                return

        self.active_changed.emit(False)
        self.status.emit(
            "Speech finished."
            if code == 0
            else "Voice playback failed; the response remains on screen."
        )
        self._play_pending()

    def _failed(self, _error: QProcess.ProcessError) -> None:
        self.timer.stop()
        self.level.emit(0)
        if self._provider == "livekit" and not self._fallback_attempted:
            self._fallback_attempted = True
            if self._start_local(self._current_text):
                return
        self.active_changed.emit(False)
        self.status.emit("Voice is unavailable; the response remains on screen.")
        self._play_pending()

    def _timeout(self) -> None:
        self.process.kill()
        self.status.emit("Voice playback timed out; the response remains on screen.")

    def _play_pending(self) -> None:
        if self.pending is not None:
            text, self.pending = self.pending, None
            self.speak(text)

    def _read_levels(self) -> None:
        if self._provider != "livekit":
            self.process.readAllStandardOutput()
            return
        self._level_buffer += bytes(self.process.readAllStandardOutput())
        lines = self._level_buffer.split(b"\n")
        self._level_buffer = lines.pop()
        for line in lines:
            if line.startswith(b"LEVEL:"):
                try:
                    self.level.emit(max(0, min(100, int(line[6:]))))
                except ValueError:
                    pass

    def stop(self) -> None:
        self.pending = None
        self.timer.stop()
        self.active_changed.emit(False)
        self.level.emit(0)
        if self.process.state() != QProcess.ProcessState.NotRunning:
            self.process.kill()
            self.process.waitForFinished(1000)
