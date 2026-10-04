"""One observable source of truth for the desktop visual lifecycle."""

from PySide6.QtCore import QObject, QTimer, Signal

STATES = {"IDLE", "LISTENING", "THINKING", "SPEAKING", "EXECUTING", "SUCCESS", "ERROR"}


class VisualState(QObject):
    changed = Signal(str)
    level_changed = Signal(float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.value = "IDLE"
        self.level = 0.0
        self._sequence = 0

    def set(self, value: str) -> None:
        value = str(value).upper()
        if value not in STATES:
            return
        self._sequence += 1
        sequence = self._sequence
        if self.value != value:
            self.value = value
            self.changed.emit(value)
        if value in {"SUCCESS", "ERROR"}:
            QTimer.singleShot(950, lambda: self._settle(sequence))

    def _settle(self, sequence: int) -> None:
        if sequence == self._sequence:
            self.set("IDLE")

    def set_level(self, level: float) -> None:
        self.level = max(0.0, min(1.0, float(level)))
        self.level_changed.emit(self.level)
