"""Floating textual status; never pretends that a microphone is active."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QLabel, QPushButton, QVBoxLayout


class AssistantOverlay(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent, Qt.WindowType.Tool | Qt.WindowType.WindowStaysOnTopHint)
        self.setWindowTitle("Lucifer · Assistant")
        self.resize(420, 240)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        self.brand = QLabel("◉  LUCIFER")
        self.brand.setObjectName("brand")
        self.state = QLabel("IDLE")
        self.state.setObjectName("state")
        self.response = QLabel("Ready for a typed command.")
        self.response.setWordWrap(True)
        self.response.setTextFormat(Qt.TextFormat.PlainText)
        dismiss = QPushButton("Dismiss")
        dismiss.clicked.connect(self.hide)
        for widget in (self.brand, self.state, self.response, dismiss):
            layout.addWidget(widget)

    def set_agent_name(self, name: str) -> None:
        self.setWindowTitle(f"{name} · Assistant")
        self.brand.setText(f"◉  {name.upper()}")

    def update_status(self, state: str, message: str) -> None:
        self.state.setText(state)
        self.response.setText(message)
