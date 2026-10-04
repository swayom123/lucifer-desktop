"""Push-to-talk controls, real input level, cancellation and offline transcription worker."""

import threading

from PySide6.QtCore import Qt, QThreadPool, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QComboBox,
    QGridLayout,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QWidget,
)

from core.models import Result
from ui.dashboard import Select
from ui.worker import Worker
from voice.microphone import Microphone
from voice.speech_to_text import SpeechToText


class VoiceControls(QWidget):
    controls_changed = Signal()
    active_changed = Signal(bool)
    recognized = Signal(str)
    status = Signal(str, str)

    def __init__(self, cache, pool: QThreadPool, parent=None):
        super().__init__(parent)
        self.pool = pool
        self.microphone = Microphone(self)
        self.stt = SpeechToText(cache)
        self.cancelled = threading.Event()
        self.active = False
        self.transcribing = False
        self.speaking = False
        self.command_busy = False
        self.hands_free = False
        self.worker = None
        layout = QGridLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.devices = Select()
        self.devices.setAccessibleName("Microphone input")
        self.devices.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
        )
        self.devices.setMinimumContentsLength(8)
        self.devices.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.devices.setMinimumWidth(0)
        self.devices.setToolTip("Microphone input; click Listen to refresh connected devices.")
        self._refresh_devices()
        self.listen = QPushButton("Listen · Ctrl+Space")
        self.listen.clicked.connect(self.toggle)
        self.cancel = QPushButton("Cancel voice")
        self.cancel.setEnabled(False)
        self.cancel.clicked.connect(self.cancel_capture)
        self.meter = QProgressBar()
        self.meter.setRange(0, 100)
        self.meter.setValue(0)
        self.meter.setTextVisible(False)
        self.meter.setFixedSize(48, 6)
        self.meter.setAccessibleName("Microphone level")
        self.meter.setToolTip("Actual microphone peak level")
        layout.addWidget(self.devices, 0, 0, 1, 2)
        layout.addWidget(self.meter, 1, 0)
        layout.addWidget(self.cancel, 1, 1)
        layout.addWidget(self.listen, 2, 0, 1, 2)
        self.microphone.level.connect(self.meter.setValue)
        self.microphone.audio.connect(self._transcribe)
        self.microphone.failed.connect(self._failed)
        self.shortcut = QShortcut(QKeySequence("Ctrl+Space"), self)
        self.shortcut.setContext(Qt.ShortcutContext.WindowShortcut)
        self.shortcut.activated.connect(self.toggle)

    def _refresh_devices(self) -> None:
        selected = self.devices.currentData()
        self.devices.clear()
        self.devices.setPlaceholderText("No microphone connected")
        for device in self.microphone.devices():
            self.devices.addItem(device.description(), bytes(device.id()))
            if selected == bytes(device.id()) or (selected is None and device.isDefault()):
                self.devices.setCurrentIndex(self.devices.count() - 1)

    def set_command_busy(self, busy: bool) -> None:
        self.command_busy = busy
        self.listen.setEnabled(
            not self.hands_free and not busy and not self.speaking and not self.transcribing
        )
        self.controls_changed.emit()

    def set_hands_free(self, active: bool) -> None:
        self.hands_free = active
        self.listen.setText("Hands-free active" if active else "Listen · Ctrl+Space")
        self.listen.setEnabled(
            not active and not self.command_busy and not self.speaking and not self.transcribing
        )
        self.devices.setEnabled(not active)
        if active:
            self.cancel.setEnabled(False)
        self.controls_changed.emit()

    def set_speaking(self, speaking: bool) -> None:
        self.speaking = speaking
        self.set_command_busy(self.command_busy)

    def toggle(self) -> None:
        if self.hands_free or self.command_busy or self.speaking or self.transcribing:
            return
        if self.microphone.recording:
            self.microphone.finish()
            return
        self._refresh_devices()
        self.active = True
        self.cancelled.clear()
        self.active_changed.emit(True)
        self.cancel.setEnabled(True)
        self.devices.setEnabled(False)
        self.listen.setText("Done listening")
        self.controls_changed.emit()
        self.status.emit(
            "LISTENING", "Listening for up to 8 seconds… Speak now, then click Done listening."
        )
        self.microphone.start(self.devices.currentData())

    def cancel_capture(self) -> None:
        self.cancelled.set()
        self.microphone.cancel()
        if self.transcribing:
            self.cancel.setEnabled(False)
            self.status.emit("THINKING", "Cancelling recognition… No action will be executed.")
        else:
            self._finish()
            self.status.emit("IDLE", "Voice command cancelled.")

    def _transcribe(self, pcm: bytes) -> None:
        self.transcribing = True
        self.listen.setEnabled(False)
        self.controls_changed.emit()
        self.status.emit("THINKING", "Recognizing speech locally…")
        self.worker = Worker(lambda emit: self.stt.transcribe(pcm, self.cancelled))
        self.worker.signals.finished.connect(self._result)
        self.pool.start(self.worker)

    def _result(self, result: Result) -> None:
        was_cancelled = self.cancelled.is_set()
        self._finish()
        if was_cancelled:
            self.status.emit("IDLE", "Voice command cancelled.")
        elif result.ok:
            self.recognized.emit(result.message)
        else:
            self.status.emit("ERROR", result.message)

    def _failed(self, message: str) -> None:
        self._finish()
        self.status.emit("ERROR", message)

    def _finish(self) -> None:
        self.active = False
        self.transcribing = False
        self.cancel.setEnabled(False)
        self.devices.setEnabled(True)
        self.listen.setText("Listen · Ctrl+Space")
        self.set_command_busy(False)
        self.active_changed.emit(False)
