"""Native command workspace with live feedback, local history and policy visibility."""

import json
import os
import re
from pathlib import Path
from time import monotonic

from PySide6.QtCore import QEvent, QProcess, QSettings, QSize, Qt, QThreadPool, QTimer, Slot
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QSystemTrayIcon,
    QTableWidget,
    QTableWidgetItem,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from automation.application_registry import ApplicationRegistry
from config.settings import Settings
from core.assistant import Assistant
from core.models import Approval, Result
from services.action_logging import read_log_tail
from services.briefing import build_briefing
from ui.assistant_overlay import AssistantOverlay
from ui.dashboard import ActionPanel, Clock, QuickCommands, Select
from ui.icons import icon
from ui.neural_visualizer import NeuralVisualizer
from ui.visual_state import VisualState
from ui.voice_controls import VoiceControls
from ui.worker import Worker
from voice.text_to_speech import LocalSpeech
from voice.wake_listener import WakeListener

NAVIGATION = ["Home", "Chat", "Apps", "Web Search", "Tasks", "Notes", "Settings"]
NAV_ICONS = ["home", "chat", "apps", "search", "task", "notes", "settings"]
NAV_PAGES = [0, 0, 2, 0, 1, 7, 9]


def label(text: str, name: str = "") -> QLabel:
    widget = QLabel(text)
    widget.setTextFormat(Qt.TextFormat.PlainText)
    widget.setWordWrap(True)
    if name:
        widget.setObjectName(name)
    return widget


def table(headers: list[str]) -> QTableWidget:
    widget = QTableWidget(0, len(headers))
    widget.setHorizontalHeaderLabels(headers)
    widget.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    widget.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    widget.verticalHeader().hide()
    widget.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
    return widget


class MainWindow(QMainWindow):
    def __init__(
        self,
        assistant: Assistant,
        apps: ApplicationRegistry,
        settings: Settings,
        background_mode: bool = False,
    ):
        super().__init__()
        self.assistant, self.apps, self.settings = assistant, apps, settings
        self.preferences = QSettings("Lucifer", "Lucifer")
        self.agent_name = str(self.preferences.value("agent_name", "Lucifer")).strip() or "Lucifer"
        self.pool = QThreadPool(self)
        self.pool.setMaxThreadCount(1)
        self.busy = False
        self.voice_reply_pending = False
        self.worker = None
        self.approval = None
        self.dialog = None
        self.background_mode = background_mode
        self.quitting = False
        self._hands_free_requested = False
        self.conversation_mode = False
        self._restore_hands_free = False
        self.conversation_started = 0.0
        self.visual_state = VisualState(self)
        self.setWindowTitle(f"{self.agent_name} · Desktop Assistant")
        self.resize(1440, 860)
        self.setMinimumSize(360, 560)
        self.overlay = AssistantOverlay(self)
        self.overlay.set_agent_name(self.agent_name)
        self.speech = LocalSpeech(self)
        self.speech.status.connect(lambda text: self.statusBar().showMessage(text))
        root = QWidget()
        self.setCentralWidget(root)
        horizontal = QHBoxLayout(root)
        horizontal.setContentsMargins(0, 0, 0, 0)
        horizontal.setSpacing(0)
        self.sidebar_layout = QVBoxLayout()
        self.sidebar_layout.setContentsMargins(20, 28, 20, 24)
        self.brand = label(self.agent_name, "brand")
        self.brand.setPixmap(icon("spark", "#91dbd1").pixmap(32, 32))
        self.brand_name = label(self.agent_name, "brand")
        brand_row = QHBoxLayout()
        brand_row.setSpacing(12)
        brand_row.addWidget(self.brand)
        brand_row.addWidget(self.brand_name, 1)
        self.sidebar_layout.addLayout(brand_row)
        self.brand_caption = label("Your desktop assistant", "muted")
        self.sidebar_layout.addWidget(self.brand_caption)
        self.sidebar_layout.addSpacing(36)
        self.navigation = QListWidget()
        self.navigation.setObjectName("navigation")
        self.navigation.setIconSize(QSize(19, 19))
        self.navigation.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        for title, symbol in zip(NAVIGATION, NAV_ICONS):
            item = QListWidgetItem(icon(symbol), title)
            item.setToolTip(title)
            item.setData(Qt.ItemDataRole.AccessibleTextRole, title)
            self.navigation.addItem(item)
        self.sidebar_layout.addWidget(self.navigation, 1)
        self.profile = label(f"{os.getenv('USER', 'Local user')}\nPersonal workspace", "profile")
        self.sidebar_layout.addWidget(self.profile)
        self.side_widget = QWidget(objectName="sidebar")
        self.side_widget.setFixedWidth(208)
        self.side_widget.setLayout(self.sidebar_layout)
        horizontal.addWidget(self.side_widget)
        shell = QWidget()
        shell_layout = QVBoxLayout(shell)
        shell_layout.setContentsMargins(0, 0, 0, 0)
        shell_layout.setSpacing(0)
        self.mobile_nav = Select()
        self.mobile_nav.setObjectName("mobileNav")
        self.mobile_nav.setAccessibleName("Navigate Lucifer")
        for title, symbol in zip(NAVIGATION, NAV_ICONS):
            self.mobile_nav.addItem(icon(symbol), title)
        self.mobile_nav.activated.connect(self.navigation.setCurrentRow)
        self.mobile_nav.hide()
        shell_layout.addWidget(self.mobile_nav)
        self.conversation_slot = QWidget()
        shell_layout.addWidget(self.conversation_slot)
        self.pages = QStackedWidget()
        self.pages.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
        shell_layout.addWidget(self.pages, 1)
        horizontal.addWidget(shell, 1)
        self._dashboard()
        # Both voice paths use the same single-thread pool, so one model can serve both.
        self.wake_listener = WakeListener(
            self.settings.data_dir / "models",
            self.pool,
            wake_word=self.settings.wake_word,
            parent=self,
            stt=self.voice_controls.stt,
        )
        self.wake_listener.command.connect(self._wake_command)
        self.wake_listener.wake_detected.connect(self._wake_detected)
        self.wake_listener.status.connect(self._voice_status)
        self.wake_listener.active_changed.connect(self.voice_controls.set_hands_free)
        self.wake_listener.active_changed.connect(self._hands_free_changed)
        self.history = table(["Time", "Action", "Result", "Duration"])
        self._page(
            "Command History",
            self.history,
            "Local action metadata only. Raw commands and argument values are not stored.",
        )
        self.application_table = table(["Application", "Availability", "Aliases"])
        self._page(
            "Application Registry",
            self.application_table,
            "Known applications discovered on this computer. Terminal requires confirmation.",
        )
        self.system_text = label("Select Refresh to read current system measurements.")
        self._page(
            "System Status",
            self.system_text,
            "Live measurements from this computer; interface status does not prove internet access.",
        )
        self._text_page("Permissions", self._policy_text())
        self._text_page(
            "Voice Settings",
            "Hands-free mode: say “Lucifer”, wait for the acknowledgement, then give a command "
            "without repeating the wake word. You can also say the wake word and command in one "
            "phrase. The local listener stays on-device.\n\n"
            "Manual mode: click Listen or press Ctrl+Space while Lucifer is focused.\n\n"
            "Choose a microphone in Home → Voice options. Standard voice commands capture up "
            "to eight seconds; Conversation mode allows longer turns and listens again after "
            "each spoken response. Use the on-screen End conversation button or say "
            "“end conversation” at any time. Speak naturally; you do not need to repeat the wake word.\n\n"
            "For standard voice commands, click "
            "Done listening. Cancel voice discards the request. Audio stays in memory and "
            "is transcribed locally with faster-whisper. No audio is uploaded.\n\n"
            "Recognized commands use the same tools and confirmation dialogs as typed commands. "
            "Results are read aloud using local Speech Dispatcher.\n\n"
            "Hands-free listening starts a few seconds after the window opens and pauses "
            "while Lucifer speaks. Conversation context stays in memory for this session, "
            "with a longer time window while the mode is active. It is not written to history "
            "or logs. Toggle conversation mode off to return to wake-word listening.",
        )
        self._text_page(
            "AI Settings",
            "Natural-language AI: configured Groq/Gemini providers with fallback.\n\n"
            "Ask questions, describe a React app, request music, or combine supported tasks. "
            "Lucifer validates each planned action and asks for confirmation before creating "
            "or running code. Questions use live web search with source links.\n\n"
            "Your request and relevant search results or build diagnostics are sent to the "
            "configured AI provider. Standard mode keeps up to eight recent turns for five "
            "minutes. Conversation mode keeps up to forty turns for up to two hours while "
            "active. This context is cleared "
            "when Lucifer exits and is never written to history or logs. Audio remains local. "
            "Keys are loaded from .env and never written to history or logs. Free-tier limits "
            "can temporarily prevent AI requests.",
        )
        self._text_page(
            "Integrations",
            "Notion calendar and notes are available when NOTION_API_KEY is configured and "
            "the relevant pages are shared with the integration. Creating meetings and notes "
            "requires confirmation.\n\nGmail and Google Calendar OAuth integrations are planned; "
            "email sending is not available.",
        )
        self.log_text = QTextBrowser()
        self._page(
            "Logs", self.log_text, "Structured action metadata; no raw command text or credentials."
        )
        self._settings_page()
        self.speech.level.connect(lambda value: self.visual_state.set_level(value / 100))
        self.wake_listener.microphone.level.connect(
            lambda value: (
                self.visual_state.set_level(value / 100)
                if self.wake_listener.awaiting_command or self.wake_listener.conversation_mode
                else None
            )
        )
        self.navigation.currentRowChanged.connect(self._navigate)
        self.navigation.setCurrentRow(0)
        self.visual_state.changed.connect(self._visual_changed)
        self.refresh_history()
        self._setup_tray()

    def _setup_tray(self) -> None:
        if not self.background_mode:
            self.tray = None
            return
        icon = self.windowIcon()
        self.tray = QSystemTrayIcon(icon, self)
        self.tray.setToolTip(f"{self.agent_name} — say {self.settings.wake_word} to wake")
        menu = QMenu(self)
        show = menu.addAction(f"Open {self.agent_name}")
        show.triggered.connect(self.show_assistant)
        menu.addSeparator()
        quit_action = menu.addAction(f"Quit {self.agent_name}")
        quit_action.triggered.connect(self.quit_from_tray)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(
            lambda reason: (
                self.show_assistant()
                if reason == QSystemTrayIcon.ActivationReason.Trigger
                else None
            )
        )
        self.tray.show()

    @Slot()
    def show_assistant(self) -> None:
        self.show()
        self.raise_()
        self.activateWindow()

    @Slot()
    def quit_from_tray(self) -> None:
        self.quitting = True
        self.close()

    @staticmethod
    def _startup_status() -> str:
        config = Path(os.getenv("XDG_CONFIG_HOME", str(Path.home() / ".config")))
        entry = config / "autostart/lucifer.desktop"
        if entry.exists():
            return "Desktop autostart entry installed (login briefing)"
        return "Manual"

    @Slot()
    def show_startup_briefing(self) -> None:
        # Do not overwrite a command the user started while the desktop was settling.
        if self.busy:
            QTimer.singleShot(1000, self.show_startup_briefing)
            return
        self.navigation.setCurrentRow(0)
        self.command_label.setText("Your login briefing")
        self._start(lambda emit: build_briefing())

    @Slot()
    def start_hands_free(self) -> None:
        """Start after login/briefing and never open the mic over Lucifer's speech."""
        self._hands_free_requested = True
        self._try_start_hands_free()

    def _try_start_hands_free(self) -> None:
        if not self._hands_free_requested:
            return
        if self.speech.process.state() != QProcess.ProcessState.NotRunning or self.busy:
            QTimer.singleShot(2000, self._try_start_hands_free)
            return
        self.wake_listener.start()

    def _page(self, title: str, content: QWidget, subtitle: str = "") -> QVBoxLayout:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(24, 28, 24, 24)
        layout.setSpacing(20)
        layout.addWidget(label(title, "title"))
        if subtitle:
            layout.addWidget(label(subtitle, "muted"))
        layout.addWidget(content, 1)
        self.pages.addWidget(page)
        return layout

    def _text_page(self, title: str, text: str) -> None:
        content = QTextBrowser()
        content.setPlainText(text)
        self._page(title, content)

    def _settings_page(self) -> None:
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setSpacing(14)
        layout.addWidget(label("ASSISTANT NAME", "eyebrow"))
        self.agent_name_input = QLineEdit(self.agent_name)
        self.agent_name_input.setMaxLength(40)
        self.agent_name_input.setPlaceholderText("Enter a name")
        self.agent_name_input.setAccessibleName("Assistant name")
        self.agent_name_input.setToolTip("Changes the name shown in the desktop interface.")
        self.agent_name_input.editingFinished.connect(self._agent_name_changed)
        layout.addWidget(self.agent_name_input)
        layout.addWidget(label("VISUAL QUALITY", "eyebrow"))
        self.quality = Select()
        self.quality.addItems(["High", "Reduced"])
        self.quality.setToolTip("Reduced mode draws fewer neural points at a lower frame rate.")
        self.quality.setCurrentText(self.preferences.value("visual_quality", "High"))
        self.quality.currentTextChanged.connect(self._quality_changed)
        layout.addWidget(self.quality)
        self.reduced_motion = QCheckBox("Reduce motion")
        self.reduced_motion.setChecked(self.preferences.value("reduced_motion", False, type=bool))
        self.reduced_motion.toggled.connect(self._motion_changed)
        layout.addWidget(self.reduced_motion)
        self.brain.set_quality(self.quality.currentText().lower())
        self.brain.set_reduced_motion(self.reduced_motion.isChecked())
        self.action_panel.set_reduced_motion(self.reduced_motion.isChecked())
        layout.addWidget(
            label(
                f"Data directory: {self.settings.data_dir}\nStartup: {self._startup_status()}\nHistory: latest 1,000 actions\nHands-free: local Whisper",
                "muted",
            )
        )
        layout.addWidget(label("MORE CONTROLS", "eyebrow"))
        for title, page in (
            ("System Status", 3),
            ("Permissions", 4),
            ("Voice Settings", 5),
            ("AI Settings", 6),
            ("Integrations", 7),
            ("Logs", 8),
        ):
            button = QPushButton(title)
            button.setIcon(icon("arrow"))
            button.clicked.connect(
                lambda checked=False, destination=page: self._settings_detail(destination)
            )
            layout.addWidget(button)
        layout.addStretch()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setWidget(content)
        self._page("Settings", scroll)

    def _settings_detail(self, page: int) -> None:
        self.navigation.setCurrentRow(-1)
        self.pages.setCurrentIndex(page)
        if page == 3 and not self.busy:
            self._start(lambda emit: self.assistant.submit("System status", emit))
        elif page == 8:
            path = self.settings.data_dir / "actions.jsonl"
            self.log_text.setPlainText(read_log_tail(path) or "No actions yet.")

    def _quality_changed(self, value: str) -> None:
        self.preferences.setValue("visual_quality", value)
        self.brain.set_quality(value.lower())

    def _agent_name_changed(self) -> None:
        name = self.agent_name_input.text().strip()
        if not name:
            self.agent_name_input.setText(self.agent_name)
            return
        self.agent_name = name
        self.preferences.setValue("agent_name", name)
        self.setWindowTitle(f"{name} · Desktop Assistant")
        self.brand_name.setText(name)
        self.hero_label.setText(name)
        self.overlay.set_agent_name(name)
        if self.tray is not None:
            self.tray.setToolTip(f"{name} — say {self.settings.wake_word} to wake")
            actions = self.tray.contextMenu().actions()
            actions[0].setText(f"Open {name}")
            actions[2].setText(f"Quit {name}")

    def _motion_changed(self, enabled: bool) -> None:
        self.preferences.setValue("reduced_motion", enabled)
        self.brain.set_reduced_motion(enabled)
        self.action_panel.set_reduced_motion(enabled)

    def _dashboard(self) -> None:
        page = QScrollArea()
        page.setObjectName("homeScroll")
        page.setWidgetResizable(True)
        page.setFrameShape(QFrame.Shape.NoFrame)
        page.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.home_content = QWidget(objectName="homePage")
        self.home_layout = QVBoxLayout(self.home_content)
        self.home_layout.setContentsMargins(36, 26, 36, 26)
        self.home_layout.setSpacing(24)
        header = QHBoxLayout()
        self.page_heading = label("Your space", "sectionTitle")
        header.addWidget(self.page_heading, 1)
        self.state_label = label("●  IDLE", "state")
        self.state_label.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        header.addWidget(self.state_label)
        header.addSpacing(20)
        self.clock = Clock()
        header.addWidget(self.clock)
        self.home_layout.addLayout(header)
        self.conversation_banner = QFrame(objectName="conversationBanner")
        self.conversation_banner.setAccessibleName("Active conversation status")
        banner_layout = QVBoxLayout(self.conversation_banner)
        banner_layout.setContentsMargins(16, 12, 12, 12)
        banner_layout.setSpacing(7)
        banner_top = QHBoxLayout()
        banner_title = QHBoxLayout()
        banner_title.setSpacing(8)
        self.conversation_badge = QLabel("●  LIVE", objectName="conversationBadge")
        self.conversation_badge.setSizePolicy(
            QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed
        )
        banner_title.addWidget(self.conversation_badge)
        banner_title.addWidget(label("Conversation mode", "conversationTitle"))
        banner_top.addLayout(banner_title, 1)
        self.conversation_clock = label("00:00  ·  0 turns", "conversationMeta")
        banner_top.addWidget(self.conversation_clock)
        banner_layout.addLayout(banner_top)
        banner_bottom = QHBoxLayout()
        self.conversation_hint = label(
            "Speak naturally. Lucifer will keep the thread between replies.",
            "conversationHint",
        )
        banner_bottom.addWidget(self.conversation_hint, 1)
        self.conversation_stop = QPushButton("End conversation", objectName="conversationStop")
        self.conversation_stop.setIcon(icon("stop"))
        self.conversation_stop.clicked.connect(lambda: self._set_conversation_mode(False))
        banner_bottom.addWidget(self.conversation_stop)
        banner_layout.addLayout(banner_bottom)
        self.conversation_banner.hide()
        self.conversation_timer = QTimer(self)
        self.conversation_timer.setInterval(1000)
        self.conversation_timer.timeout.connect(self._update_conversation_clock)
        banner_slot_layout = QVBoxLayout(self.conversation_slot)
        banner_slot_layout.setContentsMargins(16, 8, 16, 0)
        banner_slot_layout.addWidget(self.conversation_banner)
        body = QHBoxLayout()
        self.body_layout = body
        body.setSpacing(24)
        self.center_widget = QWidget()
        self.center_widget.setMaximumWidth(900)
        center = QVBoxLayout(self.center_widget)
        center.setContentsMargins(0, 0, 0, 0)
        center.setSpacing(0)
        self.brain = NeuralVisualizer(self.visual_state)
        self.brain.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        center.addWidget(self.brain, 1)
        self.hero_label = label(self.agent_name, "hero")
        self.hero_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        center.addWidget(self.hero_label)
        center.addSpacing(10)
        self.prompt = label("How can I help you today?", "subhero")
        self.prompt.setAlignment(Qt.AlignmentFlag.AlignCenter)
        center.addWidget(self.prompt)
        center.addSpacing(28)
        self.feedback = QScrollArea(objectName="feedback")
        self.feedback.setWidgetResizable(True)
        self.feedback.setFrameShape(QFrame.Shape.NoFrame)
        self.feedback.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.feedback.setFixedHeight(116)
        response_content = QWidget()
        response_layout = QVBoxLayout(response_content)
        response_layout.setContentsMargins(16, 12, 16, 12)
        response_layout.setSpacing(7)
        self.command_label = label("", "lastCommand")
        self.response = label("Ready when you are.", "response")
        self.response.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.response.setAccessibleName("Assistant response")
        response_header = QHBoxLayout()
        response_header.addWidget(self.command_label, 1)
        dismiss = QPushButton(objectName="quietButton")
        dismiss.setIcon(icon("close"))
        dismiss.setFixedSize(30, 30)
        dismiss.setToolTip("Dismiss response")
        dismiss.setAccessibleName("Dismiss response")
        dismiss.clicked.connect(self.feedback.hide)
        response_header.addWidget(dismiss)
        response_layout.addLayout(response_header)
        response_layout.addWidget(self.response)
        response_layout.addStretch()
        self.feedback.setWidget(response_content)
        self.feedback.hide()
        center.addWidget(self.feedback)
        self.composer = QFrame(objectName="composer")
        entry = QHBoxLayout(self.composer)
        entry.setContentsMargins(16, 9, 9, 9)
        entry.setSpacing(6)
        self.input = QLineEdit(objectName="commandInput")
        self.input.setPlaceholderText("Speak or type a command…")
        self.input.setAccessibleName("Command")
        self.input.setMaxLength(2000)
        self.input.setMinimumWidth(0)
        self.input.installEventFilter(self)
        self.input.returnPressed.connect(self.submit)
        self.send = QPushButton(objectName="primary")
        self.send.setIcon(icon("send", "#102725"))
        self.send.setFixedSize(44, 44)
        self.send.setAccessibleName("Send command")
        self.send.setToolTip("Send command · Enter")
        self.send.clicked.connect(self.submit)
        self.send.setEnabled(False)
        self.input.textChanged.connect(self._sync_send)
        self.mic_button = QPushButton(objectName="micButton")
        self.mic_button.setIcon(icon("mic"))
        self.mic_button.setFixedSize(44, 44)
        self.mic_button.setAccessibleName("Start or finish microphone capture")
        self.mic_button.setToolTip("Speak a command · Ctrl+Space")
        self.mic_button.clicked.connect(lambda: self.voice_controls.listen.click())
        entry.addWidget(self.input, 1)
        entry.addWidget(self.mic_button)
        entry.addWidget(self.send)
        center.addWidget(self.composer)
        center.addSpacing(12)
        self.shortcuts = QuickCommands(
            [
                ("Open VS Code", "Open VS Code"),
                ("Search Google", "Search Google for "),
                ("Screenshot", "Take a screenshot"),
                ("System info", "System status"),
            ]
        )
        self.shortcuts.selected.connect(self._shortcut)
        center.addWidget(self.shortcuts)
        center.addSpacing(16)
        footer = QHBoxLayout()
        footer.setSpacing(8)
        self.voice_options = QPushButton("Voice options", objectName="quietButton")
        self.voice_options.setIcon(icon("settings"))
        self.voice_options.setCheckable(True)
        self.voice_options.toggled.connect(self._show_voice_options)
        footer.addWidget(self.voice_options)
        self.conversation_toggle = QPushButton(
            "Start a conversation", objectName="conversationToggle"
        )
        self.conversation_toggle.setIcon(icon("chat", "#9ddbd2"))
        self.conversation_toggle.setCheckable(True)
        self.conversation_toggle.setAutoDefault(False)
        self.conversation_toggle.setAccessibleName("Start conversation mode")
        self.conversation_toggle.setToolTip(
            "Talk naturally without saying Lucifer before every turn"
        )
        self.conversation_toggle.toggled.connect(self._conversation_toggled)
        footer.addWidget(self.conversation_toggle)
        footer.addStretch()
        self.floating = QPushButton("Floating view", objectName="quietButton")
        self.floating.setIcon(icon("window"))
        self.floating.setToolTip("Open the floating assistant window")
        self.floating.clicked.connect(self.overlay.show)
        footer.addWidget(self.floating)
        center.addLayout(footer)
        self.voice_controls = VoiceControls(self.settings.data_dir / "models", self.pool, self)
        self.voice_controls.listen.hide()
        self.voice_controls.active_changed.connect(self._voice_active)
        self.voice_controls.status.connect(self._voice_status)
        self.voice_controls.recognized.connect(self._voice_recognized)
        self.voice_controls.controls_changed.connect(self._sync_microphone)
        self.speech.active_changed.connect(self._speech_active)
        self.voice_controls.microphone.level.connect(
            lambda value: self.visual_state.set_level(value / 100)
        )
        self.voice_details = QFrame(objectName="voiceDetails")
        details = QVBoxLayout(self.voice_details)
        details.setContentsMargins(12, 12, 12, 12)
        details.setSpacing(10)
        details.addWidget(self.voice_controls)
        self.hands_free = QCheckBox("Listen for the wake word")
        self.hands_free.setToolTip("Keep the local wake-word listener active")
        self.hands_free.toggled.connect(self._toggle_hands_free)
        details.addWidget(self.hands_free)
        self.voice_details.hide()
        center.addWidget(self.voice_details)
        center.addSpacing(8)
        body.addStretch(1)
        body.addWidget(self.center_widget, 10)
        body.addStretch(1)
        self.action_panel = ActionPanel()
        self.action_panel.selected.connect(self._quick_action)
        body.addWidget(self.action_panel, 0, Qt.AlignmentFlag.AlignVCenter)
        self.home_layout.addLayout(body, 1)
        page.setWidget(self.home_content)
        self.pages.addWidget(page)

    def _show_voice_options(self, visible: bool) -> None:
        self.voice_details.setVisible(visible)

    def _toggle_hands_free(self, active: bool) -> None:
        if active:
            self.start_hands_free()
        else:
            self._hands_free_requested = False
            self.wake_listener.stop()

    def _conversation_toggled(self, active: bool) -> None:
        self._set_conversation_mode(active)

    def _conversation_intent(self, command: str) -> bool | None:
        text = command.strip().casefold()
        wake_word = re.escape(self.settings.wake_word.casefold())
        text = re.sub(rf"^{wake_word}[,!. ]+", "", text).strip()
        normalized = " ".join(re.sub(r"[.!?]+$", "", text).split())
        start_phrases = {
            "start conversation",
            "start a conversation",
            "start conversation mode",
            "begin conversation",
            "begin a conversation",
            "begin conversation mode",
            "enter conversation mode",
            "enable conversation mode",
            "turn conversation mode on",
            "conversation mode on",
            "let's talk",
            "lets talk",
            "let's have a conversation",
            "let us talk",
            "can we talk",
            "can we have a conversation",
            "talk with me",
            "stay in conversation mode",
        }
        stop_phrases = {
            "end conversation",
            "end the conversation",
            "end conversation mode",
            "stop conversation",
            "stop the conversation",
            "stop conversation mode",
            "leave conversation mode",
            "turn conversation mode off",
            "conversation mode off",
            "normal mode",
            "go back to normal mode",
        }
        if normalized in start_phrases:
            return True
        if normalized in stop_phrases:
            return False
        return None

    def _set_conversation_mode(self, active: bool, *, announce: bool = True) -> None:
        active = bool(active)
        if active == self.conversation_mode:
            return
        if active and (self.busy or self.voice_controls.active):
            self.statusBar().showMessage(
                "Finish the current request before starting a conversation.", 4500
            )
            self.conversation_toggle.blockSignals(True)
            self.conversation_toggle.setChecked(False)
            self.conversation_toggle.blockSignals(False)
            return

        if active:
            self._restore_hands_free = self.wake_listener.running
            self.conversation_mode = True
            self.assistant.set_conversation_mode(True)
            self.wake_listener.set_conversation_mode(True)
            if not self.wake_listener.running:
                self.wake_listener.start()
            else:
                self.wake_listener.resume()
            self.conversation_started = monotonic()
            self.conversation_timer.start()
            self.conversation_banner.show()
            self.conversation_clock.setVisible(self.width() >= 620)
            self.conversation_toggle.setText("Conversation is on")
            self.conversation_toggle.setAccessibleName("End conversation mode")
            self.conversation_hint.setText(
                "No wake word needed · Your discussion stays in memory for this session."
            )
            self._hands_free_changed(self.wake_listener.running)
            self.hands_free.setText("Conversation mode is listening")
            self.visual_state.set("LISTENING")
            message = "Conversation mode is on. Go ahead — I’m listening."
        else:
            self.conversation_mode = False
            self.assistant.set_conversation_mode(False)
            self.wake_listener.set_conversation_mode(False)
            self.conversation_timer.stop()
            self.conversation_banner.hide()
            self.conversation_toggle.setText("Start a conversation")
            self.conversation_toggle.setAccessibleName("Start conversation mode")
            self.hands_free.setText("Listen for the wake word")
            if self._restore_hands_free:
                self.wake_listener.resume()
            else:
                self.wake_listener.stop()
            self._hands_free_changed(self.wake_listener.running)
            self.visual_state.set("IDLE")
            message = "Conversation mode is off."

        self.conversation_toggle.blockSignals(True)
        self.conversation_toggle.setChecked(active)
        self.conversation_toggle.blockSignals(False)
        self._update_conversation_clock()
        if announce:
            self.statusBar().showMessage(message, 5000)
            self.speech.speak(message)

    def _update_conversation_clock(self) -> None:
        if not self.conversation_mode:
            return
        elapsed = max(0, int(monotonic() - self.conversation_started))
        minutes, seconds = divmod(elapsed, 60)
        self.conversation_clock.setText(
            f"{minutes:02d}:{seconds:02d}  ·  {self.assistant.conversation.turn_count} turns"
        )

    def _hands_free_changed(self, active: bool) -> None:
        self.hands_free.blockSignals(True)
        self.hands_free.setChecked(active)
        self.hands_free.setText(
            "Conversation mode is listening"
            if self.conversation_mode
            else "Listen for the wake word"
        )
        self.hands_free.setEnabled(not self.conversation_mode)
        self.hands_free.blockSignals(False)

    def _sync_send(self) -> None:
        self.send.setEnabled(bool(self.input.text().strip()) and not self.busy)
        self.conversation_toggle.setEnabled(not self.busy or self.conversation_mode)

    def _sync_microphone(self) -> None:
        self.mic_button.setEnabled(self.voice_controls.listen.isEnabled())
        self.mic_button.setToolTip(self.voice_controls.listen.text() + " · Ctrl+Space")
        self.mic_button.setIcon(icon("stop" if self.voice_controls.active else "mic"))

    def _visual_changed(self, value: str) -> None:
        self.state_label.setText(f"●  {value}")
        self.state_label.setProperty("state", value.lower())
        self.state_label.style().unpolish(self.state_label)
        self.state_label.style().polish(self.state_label)
        self.composer.setProperty("listening", value == "LISTENING")
        self.composer.style().unpolish(self.composer)
        self.composer.style().polish(self.composer)

    def eventFilter(self, watched, event):
        if watched is getattr(self, "input", None) and event.type() in {
            QEvent.Type.FocusIn,
            QEvent.Type.FocusOut,
        }:
            self.composer.setProperty("focused", event.type() == QEvent.Type.FocusIn)
            self.composer.style().unpolish(self.composer)
            self.composer.style().polish(self.composer)
        return super().eventFilter(watched, event)

    def _shortcut(self, command: str) -> None:
        self.navigation.setCurrentRow(0)
        self.input.setText(command)
        self.input.setFocus()
        if not command.endswith(" "):
            self.submit()

    def _quick_action(self, action: str) -> None:
        if action == "recent":
            self.navigation.setCurrentRow(4)
            return
        templates = {"open": "Open ", "search": "Search Google for ", "ask": "", "task": ""}
        if not (action == "search" and self.navigation.currentRow() == 3):
            self.navigation.setCurrentRow(0)
        self.input.setText(templates[action])
        self.input.setFocus()

    def _policy_text(self) -> str:
        lines = [
            "LEVEL 1 · Automatic",
            "Known apps, web search, URLs, screenshots and system info.",
            "",
            "LEVEL 2 · Explicit confirmation",
            "Folder creation and terminal launch.",
            "",
            "LEVEL 3 · Always confirm",
            "Reserved for sensitive actions. No destructive tools are registered.",
            "",
            "Confirmations expire after 120 seconds and cannot be replayed.",
            "Arbitrary shell commands and sudo are not supported. Coding workflows require confirmation.",
            "",
            "Registered tools:",
        ]
        lines.extend(
            f"• {tool.name} — level {tool.level.value}"
            for tool in self.assistant.registry.definitions()
        )
        lines.append("open_application raises terminal requests to level 2.")
        return "\n".join(lines)

    @Slot(bool)
    def _speech_active(self, active: bool) -> None:
        self.voice_controls.set_speaking(active)
        if active:
            self.wake_listener.pause()
        if not self.busy:
            self._state(
                "SPEAKING" if active else ("LISTENING" if self.conversation_mode else "IDLE")
            )
        if not active and self.wake_listener.running and not self.busy:
            self.wake_listener.resume()

    @Slot(bool)
    def _voice_active(self, active: bool) -> None:
        self.busy = active
        self._sync_send()
        self.input.setEnabled(not active)

    @Slot(str)
    def _wake_command(self, text: str) -> None:
        self.show_assistant()
        if not self.conversation_mode and self._conversation_intent(text) is not True:
            self.overlay.show()
        self.voice_reply_pending = True
        self.input.setText(text)
        self.submit()

    @Slot()
    def _wake_detected(self) -> None:
        self.show_assistant()
        self.overlay.show()
        self.speech.speak("Yes, how can I help?")

    @Slot(str, str)
    def _voice_status(self, state: str, message: str) -> None:
        if state != "IDLE":
            self.response.setText(message)
            self.feedback.show()
        self._state(state)

    @Slot(str)
    def _voice_recognized(self, text: str) -> None:
        self.voice_reply_pending = True
        self.input.setText(text)
        self.submit()

    @Slot()
    def submit(self) -> None:
        if self.busy or not self.input.text().strip():
            return
        command = self.input.text().strip()
        conversation_intent = self._conversation_intent(command)
        if conversation_intent is not None:
            self.input.clear()
            self.command_label.setText("Conversation mode")
            self.voice_reply_pending = False
            self._set_conversation_mode(conversation_intent)
            return
        self.feedback.show()
        self.command_label.setText(command)
        self.input.clear()
        self.response.setText("Processing…")
        self._start(lambda emit: self.assistant.submit(command, emit))

    def _start(self, operation) -> None:
        self.busy = True
        self.feedback.show()
        self.wake_listener.pause()
        self.send.setEnabled(False)
        self.input.setEnabled(False)
        self.voice_controls.set_command_busy(True)
        self.worker = Worker(operation)
        self.worker.signals.state.connect(self._state)
        self.worker.signals.finished.connect(self._finished)
        self.pool.start(self.worker)

    @Slot(str)
    def _state(self, state: str) -> None:
        if (
            str(state).upper() == "IDLE"
            and self.visual_state.value == "SPEAKING"
            and self.speech.process.state() != QProcess.ProcessState.NotRunning
        ):
            return
        self.visual_state.set(state)
        self.input.setProperty("listening", str(state).upper() == "LISTENING")
        self.input.style().unpolish(self.input)
        self.input.style().polish(self.input)
        message = (
            "Allow screen capture in the desktop dialog if prompted."
            if (state == "EXECUTING" and "screenshot" in self.command_label.text().lower())
            else self.response.text()
        )
        self.overlay.update_status(state, message)
        if state == "EXECUTING":
            self.response.setText(
                message
                if "screenshot" in self.command_label.text().lower()
                else "Executing desktop action…"
            )

    @Slot(object)
    def _finished(self, result: Result | Approval) -> None:
        self.refresh_history()
        self.feedback.show()
        if isinstance(result, Approval):
            self.approval = result
            self.state_label.setText("●  AWAITING CONFIRMATION")
            self.response.setText("Review the action in the confirmation dialog.")
            self.dialog = QMessageBox(self)
            self.dialog.setWindowTitle(f"Lucifer · Level {result.level.value} confirmation")
            self.dialog.setIcon(QMessageBox.Icon.Question)
            self.dialog.setTextFormat(Qt.TextFormat.PlainText)
            self.dialog.setText(f"{result.description}?")
            self.dialog.setInformativeText(json.dumps(result.action.arguments, indent=2))
            self.dialog.setStandardButtons(
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel
            )
            self.dialog.setDefaultButton(QMessageBox.StandardButton.Cancel)
            self.dialog.finished.connect(self._approval_finished)
            self.dialog.open()
            if self.voice_reply_pending or self.conversation_mode:
                self.speech.speak("Please review the action and confirm it in the dialog.")
            return
        self.busy = False
        self._sync_send()
        self.input.setEnabled(True)
        self.voice_controls.set_command_busy(False)
        self.response.setText(result.message)
        self._state("SUCCESS" if result.ok else "ERROR")
        self.overlay.update_status("SUCCESS" if result.ok else "ERROR", result.message)
        if result.code == "STARTUP_BRIEFING" or self.voice_reply_pending or self.conversation_mode:
            if (
                self.voice_reply_pending
                and result.code == "AI_CLARIFICATION"
                and not self.conversation_mode
            ):
                self.wake_listener.prepare_follow_up()
            self.voice_reply_pending = False
            self.speech.speak(result.data.get("spoken", result.message))
        elif self.wake_listener.running:
            self.wake_listener.resume()
        if result.code == "SYSTEM_INFO":
            self.system_text.setText(result.message)
        self.input.setFocus()

    @Slot(int)
    def _approval_finished(self, choice: int) -> None:
        approval = self.approval
        self.approval = None
        if choice == QMessageBox.StandardButton.Yes:
            self._start(lambda emit: self.assistant.confirm(approval.token, emit))
        else:
            self._finished(self.assistant.decline(approval))

    def refresh_history(self) -> None:
        rows = self.assistant.database.recent()
        self.history.setRowCount(len(rows))
        for row, item in enumerate(rows):
            for column, value in enumerate(
                [
                    item["time"][:19].replace("T", " ") + " UTC",
                    item["command"],
                    item["code"],
                    f"{item['duration_ms']} ms",
                ]
            ):
                self.history.setItem(row, column, QTableWidgetItem(str(value)))

    @Slot(int)
    def _navigate(self, index: int) -> None:
        page = NAV_PAGES[index] if 0 <= index < len(NAV_PAGES) else 0
        self.pages.setCurrentIndex(page)
        if index >= 0:
            self.mobile_nav.setCurrentIndex(index)
        if page == 1:
            self.refresh_history()
        elif page == 2:
            rows = self.apps.discover()
            self.application_table.setRowCount(len(rows))
            for row, item in enumerate(rows):
                values = [
                    item["name"],
                    "Detected" if item["installed"] else "Not detected",
                    item["aliases"],
                ]
                for column, value in enumerate(values):
                    self.application_table.setItem(row, column, QTableWidgetItem(value))
        elif page == 8:
            path = self.settings.data_dir / "actions.jsonl"
            self.log_text.setPlainText(read_log_tail(path) or "No actions yet.")
        if index == 1:
            self.input.setFocus()
        elif index == 3:
            self._quick_action("search")

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if not hasattr(self, "action_panel"):
            return
        width = self.width()
        mobile = width < 620
        compact = width < 1080
        self.side_widget.setVisible(not mobile)
        self.mobile_nav.setVisible(mobile)
        self.side_widget.setFixedWidth(76 if compact else 208)
        self.sidebar_layout.setContentsMargins(14 if compact else 20, 28, 14 if compact else 20, 24)
        self.brand_name.setVisible(not compact)
        self.brand_caption.setVisible(not compact)
        self.profile.setVisible(not compact)
        for index, name in enumerate(NAVIGATION):
            self.navigation.item(index).setText("" if compact else name)
        self.action_panel.setVisible(width >= 1280 and self.height() >= 720)
        if self.conversation_mode:
            self.conversation_clock.setVisible(width >= 620)
        self.home_layout.setContentsMargins(
            16 if mobile else 32, 20 if mobile else 26, 16 if mobile else 32, 20
        )
        self.home_layout.setSpacing(16 if mobile else 24)
        self.body_layout.setStretch(0, 0 if width < 1280 else 1)
        self.body_layout.setStretch(2, 0 if width < 1280 else 1)
        self.shortcuts.reflow(2 if width < 800 else 4)
        self.input.setPlaceholderText("Type a command…" if mobile else "Speak or type a command…")
        self.page_heading.setVisible(not mobile)
        self.brain.setMinimumHeight(180 if mobile else 220)
        self.floating.setText("" if mobile else "Floating view")
        self.floating.setAccessibleName("Open floating assistant")

    def changeEvent(self, event) -> None:
        super().changeEvent(event)
        if event.type() == QEvent.Type.WindowStateChange and hasattr(self, "brain"):
            self.brain.set_paused(self.isMinimized())

    def closeEvent(self, event) -> None:
        if self.background_mode and not self.quitting:
            self.hide()
            event.ignore()
            return
        if self.busy:
            self.statusBar().showMessage(
                "Finish or cancel the pending action before quitting.", 5000
            )
            event.ignore()
            return
        self._hands_free_requested = False
        self.assistant.set_conversation_mode(False)
        self.conversation_timer.stop()
        self.voice_controls.microphone.cancel()
        self.wake_listener.stop()
        if hasattr(self.assistant, "cleanup"):
            self.assistant.cleanup()
        if self.tray:
            self.tray.hide()
        self.speech.stop()
        self.overlay.close()
        event.accept()
