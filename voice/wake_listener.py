"""Local, hands-free wake phrase listener.

This is deliberately a conservative Whisper-based listener. It only forwards a transcript
when the configured wake word is present, and it never sends microphone data to a service.
"""

import re
import threading

from PySide6.QtCore import QObject, QThreadPool, QTimer, Signal

from core.models import Result
from ui.worker import Worker
from voice.microphone import Microphone
from voice.speech_to_text import SpeechToText, pcm_rms


class WakeListener(QObject):
    command = Signal(str)
    wake_detected = Signal()
    status = Signal(str, str)
    active_changed = Signal(bool)

    def __init__(
        self,
        cache,
        pool: QThreadPool,
        wake_word: str = "lucifer",
        parent=None,
        *,
        stt: SpeechToText | None = None,
    ):
        super().__init__(parent)
        self.pool = pool
        self.wake_word = wake_word.casefold().strip() or "lucifer"
        self.microphone = Microphone(self)
        self.stt = stt if stt is not None else SpeechToText(cache)
        self.cancelled = threading.Event()
        self.running = False
        self.conversation_mode = False
        self.paused = False
        self.awaiting_command = False
        self.transcribing = False
        self.worker = None
        self.restart = QTimer(self)
        self.restart.setSingleShot(True)
        self.restart.timeout.connect(self._listen)
        self.microphone.audio.connect(self._transcribe)
        self.microphone.failed.connect(self._failed)

    def start(self) -> None:
        if self.running:
            return
        self.running = True
        self.paused = False
        self.active_changed.emit(True)
        self._listen()

    def stop(self) -> None:
        self.running = False
        self.conversation_mode = False
        self.paused = False
        self.awaiting_command = False
        self.cancelled.set()
        self.restart.stop()
        self.microphone.cancel()
        self.stt.release_model()
        self.active_changed.emit(False)

    def set_conversation_mode(self, active: bool) -> None:
        self.conversation_mode = bool(active)
        self.paused = True
        self.cancelled.set()
        self.restart.stop()
        self.microphone.cancel()

    def pause(self) -> None:
        self.paused = True
        self.cancelled.set()
        self.restart.stop()
        self.microphone.cancel()

    def resume(self) -> None:
        if not self.running:
            return
        self.paused = False
        self.cancelled.clear()
        self.restart.start(350)

    def prepare_follow_up(self) -> None:
        """Keep the listener ready for an answer to Lucifer's clarification."""
        if self.running:
            self.awaiting_command = True

    def _listen(self) -> None:
        if not self.running or self.paused or self.transcribing:
            return
        self.cancelled.clear()
        if self.conversation_mode:
            self.status.emit("LISTENING", "Conversation mode is on — speak whenever you’re ready.")
            self.microphone.start(duration_ms=20000)
        elif self.awaiting_command:
            self.status.emit("LISTENING", "Listening for your command…")
            self.microphone.start(duration_ms=8000)
        else:
            self.status.emit(
                "IDLE", f"Hands-free active — say “{self.wake_word.capitalize()}” to wake Lucifer."
            )
            self.microphone.start(duration_ms=3500)

    def _transcribe(self, pcm: bytes) -> None:
        if not self.running or self.paused:
            return
        if pcm_rms(pcm) < 0.004:
            self.awaiting_command = False
            self.restart.start(100)
            return
        self.transcribing = True
        self.status.emit(
            "THINKING",
            "Transcribing your thought locally…"
            if self.conversation_mode
            else (
                "Recognizing your command locally…"
                if self.awaiting_command
                else "Checking for the Lucifer wake word locally…"
            ),
        )
        self.worker = Worker(lambda emit: self.stt.transcribe(pcm, self.cancelled))
        self.worker.signals.finished.connect(self._result)
        self.pool.start(self.worker)

    def _result(self, result: Result) -> None:
        self.transcribing = False
        if not self.running or self.paused:
            return
        if self.conversation_mode:
            if result.ok:
                self.pause()
                self.status.emit("THINKING", "I’m with you — give me a moment.")
                self.command.emit(result.message.strip())
            else:
                if result.code not in {"NO_SPEECH", "VOICE_CANCELLED"}:
                    self.status.emit("ERROR", result.message)
                self.restart.start(150)
            return
        if self.awaiting_command:
            self.awaiting_command = False
            if result.ok:
                self.pause()
                self.status.emit("LISTENING", "Command heard; processing your request…")
                self.command.emit(result.message.strip())
            else:
                self.restart.start(100)
            return
        wake_match = (
            re.search(
                rf"(?<!\w){re.escape(self.wake_word)}(?!\w)",
                result.message,
                flags=re.IGNORECASE,
            )
            if result.ok
            else None
        )
        if wake_match:
            remainder = result.message[wake_match.end() :].lstrip(",! .").strip()
            self.pause()
            if remainder:
                self.status.emit("LISTENING", "Wake word detected; processing your command…")
                self.command.emit(remainder)
            else:
                self.awaiting_command = True
                self.status.emit("LISTENING", "Yes, how can I help?")
                self.wake_detected.emit()
            return
        self.restart.start(100)

    def _failed(self, message: str) -> None:
        if self.running and not self.paused:
            self.awaiting_command = False
            text = (
                f"Conversation mode remains on, but the microphone needs attention: {message}"
                if self.conversation_mode
                else f"Hands-free listening paused: {message}"
            )
            self.status.emit("ERROR", text)
            self.restart.start(3000)
