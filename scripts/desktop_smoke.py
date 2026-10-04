"""Opt-in live UI smoke test; opens real apps/browser and requests screenshot consent."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from config.settings import Settings
from core.bootstrap import build
from ui.main_window import MainWindow
from ui.theme import STYLESHEET

app = QApplication(sys.argv)
app.setStyle("Fusion")
app.setStyleSheet(STYLESHEET)
settings = Settings.load()
assistant, applications = build(settings)
window = MainWindow(assistant, applications, settings)
window.show()
commands = (
    ["Take a screenshot"]
    if "--screenshot-only" in sys.argv
    else ["Open VS Code", "Search Google for Python decorators", "Take a screenshot"]
)
results = []
started = False


def advance():
    global started
    if window.busy:
        return
    if started:
        latest = assistant.database.recent(1)[0]
        results.append(latest)
        print(json.dumps(latest), flush=True)
        print(window.response.text(), flush=True)
        started = False
    if commands:
        window.input.setText(commands.pop(0))
        window.submit()
        started = True
    else:
        window.grab().save(str(settings.data_dir / "desktop-smoke-ui.png"))
        (settings.data_dir / "desktop-smoke.json").write_text(json.dumps(results, indent=2))
        timer.stop()
        window.close()
        app.exit(0 if all(result["ok"] for result in results) else 1)


timer = QTimer()
timer.timeout.connect(advance)
timer.start(500)
raise SystemExit(app.exec())
