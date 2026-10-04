"""Lucifer's shared palette, type scale and native component treatments."""

from pathlib import Path

STYLESHEET = """
QWidget { background: #0e141d; color: #e2e8ef; font-family: "Lato"; font-size: 14px; }
QMainWindow, QWidget#homePage, QScrollArea#homeScroll { background: #0e141d; }
QWidget#sidebar { background: #111923; border-right: 1px solid #222d3b; }
QLabel { background: transparent; }
QLabel#brand { color: #f0f4f7; font-size: 24px; font-weight: 700; }
QLabel#title { color: #edf2f7; font-size: 28px; font-weight: 700; }
QLabel#hero { color: #edf2f7; font-size: 40px; font-weight: 600; }
QLabel#subhero { color: #a6b3c3; font-size: 17px; }
QLabel#muted, QLabel#profile { color: #97a6b8; font-size: 13px; }
QLabel#profile { border-top: 1px solid #26313f; padding-top: 20px; }
QLabel#eyebrow { color: #9babbc; font-size: 11px; font-weight: 700; letter-spacing: 1px; }
QLabel#sectionTitle { color: #aab6c5; font-size: 13px; font-weight: 600; }
QLabel#state { color: #8ed1c4; font-size: 10px; font-weight: 700; letter-spacing: 1px; padding: 7px 10px; border: 1px solid #2a4144; border-radius: 12px; background: #152528; }
QLabel#state[state="error"] { color: #e5a4b8; background: #30212a; border-color: #523546; }
QLabel#state[state="thinking"], QLabel#state[state="speaking"] { color: #bab2e9; background: #242238; border-color: #3e3956; }
QLabel#clockTime { color: #d9e3ed; font-size: 16px; font-weight: 600; }
QLabel#clockDate { color: #94a3b6; font-size: 12px; }
QLabel#lastCommand { color: #8fbcb8; font-size: 12px; font-weight: 600; }
QLabel#response { color: #d0dae6; font-size: 14px; }
QScrollArea#feedback { background: #151f2b; border: 1px solid #2b3746; border-radius: 12px; margin-bottom: 12px; }
QScrollArea#feedback QWidget { background: transparent; }
QFrame#actionPanel { background: transparent; border: none; }
QFrame#composer { background: #192330; border: 1px solid #3b4b5d; border-radius: 16px; }
QFrame#composer[focused="true"] { border-color: #76bdb9; }
QFrame#composer[listening="true"] { border-color: #8bdfd0; background: #192e33; }
QFrame#voiceDetails { background: #141e2a; border: 1px solid #293647; border-radius: 12px; }
QFrame#voiceDetails QWidget { background: transparent; }
QPushButton { background: #1c2938; border: 1px solid #334257; border-radius: 9px; padding: 10px 14px; color: #d9e2ec; min-height: 18px; }
QPushButton:hover { background: #26374a; border-color: #617e95; }
QPushButton:pressed { background: #30475a; }
QPushButton:focus { border: 1px solid #9cddd6; }
QPushButton:disabled { color: #728298; border-color: #283546; background: #16202d; }
QPushButton#primary { background: #a0ded2; border: 1px solid #a0ded2; border-radius: 11px; padding: 0; }
QPushButton#primary:hover { background: #bceadf; }
QPushButton#primary:pressed { background: #79bfb4; }
QPushButton#primary:focus { border: 2px solid #f0fff9; }
QPushButton#primary:disabled { background: #36554f; border-color: #36554f; }
QPushButton#micButton { background: transparent; border: 1px solid transparent; padding: 0; border-radius: 11px; }
QPushButton#micButton:hover { background: #2b3d4e; }
QPushButton#micButton:focus { border-color: #9cddd6; }
QPushButton#chip { background: transparent; color: #aab9c9; border: 1px solid #2a384a; border-radius: 9px; padding: 8px 10px; font-size: 12px; }
QPushButton#chip:hover { color: #e3f1f0; background: #1c2b39; border-color: #55777a; }
QPushButton#chip:focus { border-color: #9cddd6; }
QPushButton#quietButton { background: transparent; border: 1px solid transparent; color: #9aabbd; font-size: 12px; padding: 5px 7px; }
QPushButton#quietButton:hover, QPushButton#quietButton:checked { background: #1b2937; color: #d4e2ef; }
QPushButton#quietButton:focus { border-color: #9cddd6; }
QLineEdit { background: #182332; border: 1px solid #435369; border-radius: 10px; padding: 12px; selection-background-color: #386d71; }
QLineEdit:focus { border-color: #9cddd6; }
QLineEdit#commandInput { background: transparent; border: none; padding: 8px 0; font-size: 15px; }
QListWidget { background: transparent; border: 0; outline: 0; }
QListWidget::item { padding: 12px 10px; margin: 3px 0; border: 1px solid transparent; border-radius: 9px; color: #9eafc2; }
QListWidget::item:hover { background: #1a2837; color: #dde8f1; }
QListWidget::item:selected { background: #20353b; color: #b3e2d9; border: 1px solid #304b50; }
QListWidget::item:focus { border-color: #85bfb8; }
QTableWidget { background: #141e2b; alternate-background-color: #182431; border: 1px solid #2c3a4c; border-radius: 10px; gridline-color: #263344; selection-background-color: #2a4852; }
QTableWidget::item { padding: 8px; }
QHeaderView::section { background: #1b2939; color: #b6c4d3; padding: 12px; border: 0; font-size: 12px; font-weight: 600; }
QTextBrowser, QPlainTextEdit { background: #141e2b; border: 1px solid #2c3a4c; border-radius: 12px; padding: 18px; }
QComboBox { background: #182534; border: 1px solid #3b4e64; border-radius: 8px; padding: 10px 12px; min-height: 18px; }
QComboBox:focus { border-color: #9cddd6; }
QComboBox::down-arrow { image: none; }
QComboBox::drop-down { border: none; width: 24px; }
QComboBox QAbstractItemView { background: #1b2a3b; selection-background-color: #2a4852; padding: 5px; }
QComboBox#mobileNav { margin: 10px 16px 0 16px; }
QProgressBar { background: #27394b; border: 0; border-radius: 3px; }
QProgressBar::chunk { background: #83cbbb; border-radius: 3px; }
QCheckBox { spacing: 10px; padding: 6px 0; }
QCheckBox::indicator { width: 18px; height: 18px; background: #182534; border: 1px solid #718598; border-radius: 4px; }
QCheckBox::indicator:checked { background: #a0ded2; border-color: #a0ded2; image: url(CHECK_ASSET); }
QCheckBox::indicator:hover { border-color: #bce9df; }
QCheckBox:focus { color: #c4f0e6; }
QScrollBar:vertical { background: transparent; width: 7px; margin: 2px; }
QScrollBar::handle:vertical { background: #415569; border-radius: 3px; min-height: 28px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
QToolTip { background: #243547; color: #e3edf5; border: 1px solid #526a81; padding: 6px; }
QStatusBar { color: #9aadc2; font-size: 12px; }
QMessageBox QLabel { min-width: 240px; }
""".replace("CHECK_ASSET", (Path(__file__).parent / "assets/check.svg").as_posix())
STYLESHEET += """
QFrame#conversationBanner { background: #18292c; border: 1px solid #3a5d59; border-radius: 12px; }
QFrame#conversationBanner QWidget { background: transparent; }
QLabel#conversationBadge { background: #22433e; color: #a9e1d3; border: 1px solid #3d6a60; border-radius: 9px; padding: 5px 8px; font-size: 10px; font-weight: 700; letter-spacing: 1px; }
QLabel#conversationTitle { color: #e3f1ec; font-size: 14px; font-weight: 650; }
QLabel#conversationMeta { color: #acc7bf; font-size: 12px; }
QLabel#conversationHint { color: #a9beb9; font-size: 12px; }
QPushButton#conversationStop { background: #263538; border: 1px solid #4d6968; color: #e6f0ed; padding: 8px 11px; min-height: 16px; }
QPushButton#conversationStop:hover { background: #314648; border-color: #94c8bd; }
QPushButton#conversationToggle { background: transparent; border: 1px solid #37524f; color: #b7ddd3; border-radius: 9px; padding: 7px 10px; font-size: 12px; }
QPushButton#conversationToggle:hover { background: #1e3536; border-color: #73aaa0; }
QPushButton#conversationToggle:checked { background: #24413d; border-color: #76b6aa; color: #d4f4ea; }
QPushButton#conversationToggle:checked:hover { background: #2c4e49; }
QPushButton#conversationToggle:disabled { color: #7d918b; border-color: #334542; }

"""
