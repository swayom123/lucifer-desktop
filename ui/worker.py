"""Keep desktop I/O and portal waits off Qt's GUI thread."""

from collections.abc import Callable

from PySide6.QtCore import QObject, QRunnable, Signal, Slot


class Signals(QObject):
    state = Signal(str)
    finished = Signal(object)


class Worker(QRunnable):
    def __init__(self, operation: Callable):
        super().__init__()
        self.operation = operation
        self.signals = Signals()

    @Slot()
    def run(self):
        from core.models import Result

        try:
            result = self.operation(self.signals.state.emit)
        except Exception:  # noqa: BLE001 — isolate adapter failures without leaking secrets
            result = Result(
                False,
                "INTERNAL_ERROR",
                "Lucifer could not finish this request. Check storage and desktop access.",
            )
        self.operation = None  # Release captured audio/arguments after this one-shot job.
        self.signals.finished.emit(result)
