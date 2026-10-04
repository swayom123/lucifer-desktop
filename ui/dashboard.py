"""Focused home controls with native keyboard access and restrained motion."""

from datetime import datetime

from PySide6.QtCore import QEasingCurve, QRect, QSize, Qt, QTimer, QVariantAnimation, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (
    QAbstractButton,
    QComboBox,
    QFrame,
    QGridLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ui.icons import icon


class Select(QComboBox):
    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        icon("chevron").paint(
            painter,
            QRect(
                self.width() - (40 if self.objectName() == "mobileNav" else 24),
                (self.height() - 14) // 2,
                14,
                14,
            ),
        )
        painter.end()


class Clock(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        self.time = QLabel(objectName="clockTime")
        self.date = QLabel(objectName="clockDate")
        for item in (self.time, self.date):
            item.setAlignment(Qt.AlignmentFlag.AlignRight)
            layout.addWidget(item)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self.timer.start(1000)
        self.refresh()

    def refresh(self):
        now = datetime.now().astimezone()
        self.time.setText(now.strftime("%I:%M %p").lstrip("0"))
        self.date.setText(now.strftime("%a, %d %b %Y"))
        self.setToolTip(now.strftime("%Z · %A, %d %B %Y"))


class ActionCard(QAbstractButton):
    """A single semantic button; its typography does not rely on padded text."""

    def __init__(self, symbol, title, subtitle, parent=None):
        super().__init__(parent)
        self.title, self.subtitle = title, subtitle
        self.symbol = icon(symbol, "#9ecbc8")
        self.arrow = icon("arrow", "#8191a4")
        self.setAccessibleName(title)
        self.setAccessibleDescription(subtitle)
        self.setToolTip(subtitle)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setFixedHeight(80)
        self.hover = 0.0
        self.motion = True
        self.animation = QVariantAnimation(self)
        self.animation.setDuration(180)
        self.animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.animation.valueChanged.connect(self._animate)

    def sizeHint(self):
        return QSize(248, 80)

    def _animate(self, value):
        self.hover = float(value)
        self.update()

    def _transition(self, target):
        self.animation.stop()
        if not self.motion:
            self._animate(target)
            return
        self.animation.setStartValue(self.hover)
        self.animation.setEndValue(target)
        self.animation.start()

    def enterEvent(self, event):
        self._transition(1.0)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._transition(0.0)
        super().leaveEvent(event)

    def keyPressEvent(self, event):
        if event.key() in {Qt.Key.Key_Return, Qt.Key.Key_Enter}:
            self.click()
            event.accept()
        else:
            super().keyPressEvent(event)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        h = self.hover
        p.setBrush(QColor(19 + int(h * 5), 27 + int(h * 8), 37 + int(h * 8)))
        p.setPen(
            QPen(
                QColor("#7acac4")
                if self.hasFocus()
                else QColor(36 + int(h * 15), 48 + int(h * 20), 61 + int(h * 20)),
                1,
            )
        )
        p.drawRoundedRect(self.rect().adjusted(1, 1, -1, -1), 12, 12)
        self.symbol.paint(p, QRect(16, 20, 20, 20))
        font = self.font()
        font.setPixelSize(14)
        font.setWeight(QFont.Weight.DemiBold)
        p.setFont(font)
        p.setPen(QColor("#e5eaf0"))
        p.drawText(QRect(48, 15, self.width() - 77, 24), Qt.AlignmentFlag.AlignVCenter, self.title)
        font.setPixelSize(12)
        font.setWeight(QFont.Weight.Normal)
        p.setFont(font)
        p.setPen(QColor("#9aa9b9"))
        p.drawText(
            QRect(48, 42, self.width() - 58, 20), Qt.AlignmentFlag.AlignVCenter, self.subtitle
        )
        self.arrow.paint(p, QRect(self.width() - 30, 20, 14, 14))
        p.end()


class ActionPanel(QFrame):
    selected = Signal(str)
    ACTIONS = (
        ("apps", "Open an app", "Launch a desktop application", "open"),
        ("search", "Search the web", "Find answers and useful links", "search"),
        ("spark", "Ask anything", "Answers, ideas and explanations", "ask"),
        ("task", "Run a task", "Automate a desktop action", "task"),
        ("history", "Recent activity", "Review your command history", "recent"),
    )

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("actionPanel")
        self.setFixedWidth(260)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        heading = QLabel("Explore what you can do", objectName="sectionTitle")
        layout.addWidget(heading)
        layout.addSpacing(6)
        self.cards = []
        for symbol, title, subtitle, key in self.ACTIONS:
            button = ActionCard(symbol, title, subtitle)
            button.clicked.connect(lambda checked=False, action=key: self.selected.emit(action))
            layout.addWidget(button)
            self.cards.append(button)
        layout.addStretch()

    def set_reduced_motion(self, enabled):
        for card in self.cards:
            card.motion = not enabled
            if enabled:
                card.animation.stop()


class QuickCommands(QWidget):
    selected = Signal(str)

    def __init__(self, actions, parent=None):
        super().__init__(parent)
        self.grid = QGridLayout(self)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setSpacing(8)
        self.buttons = []
        self.columns = 0
        for title, command in actions:
            button = QPushButton(title, objectName="chip")
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setToolTip(command.strip())
            button.clicked.connect(lambda checked=False, text=command: self.selected.emit(text))
            self.buttons.append(button)
        self.reflow(4)

    def reflow(self, columns):
        if self.columns == columns:
            return
        self.columns = columns
        for button in self.buttons:
            self.grid.removeWidget(button)
            button.setMinimumHeight(26 if columns == 2 else 18)
        for i, button in enumerate(self.buttons):
            self.grid.addWidget(button, i // columns, i % columns)
        for i in range(4):
            self.grid.setColumnStretch(i, 1 if i < columns else 0)
