"""Run Lucifer as a native desktop application: python main.py."""

import argparse
import os
import sys


def main() -> int:
    parser = argparse.ArgumentParser(description="Lucifer desktop assistant")
    parser.add_argument("--startup", action="store_true", help="Show and speak a login briefing")
    parser.add_argument(
        "--background", action="store_true", help="Run in the tray without showing the window"
    )
    arguments = parser.parse_args()
    if os.name == "posix":
        os.umask(0o077)
    from PySide6.QtCore import QLockFile, QTimer
    from PySide6.QtGui import QIcon
    from PySide6.QtWidgets import QApplication, QMessageBox

    from config.settings import ROOT, Settings
    from core.bootstrap import build
    from ui.activation import instance_name, listen_for_activation, show_existing
    from ui.main_window import MainWindow
    from ui.theme import STYLESHEET

    application = QApplication(sys.argv)
    application.setApplicationName("Lucifer")
    application.setOrganizationName("Lucifer")
    application.setWindowIcon(QIcon(str(ROOT / "assets/lucifer.svg")))
    application.setStyle("Fusion")
    application.setStyleSheet(STYLESHEET)
    settings = Settings.load()
    lock = QLockFile(str(settings.data_dir / "lucifer.lock"))
    lock.setStaleLockTime(0)
    activation_name = instance_name(settings.data_dir)
    if not lock.tryLock(100):
        if show_existing(activation_name):
            return 0
        if arguments.startup:
            return 0
        QMessageBox.information(
            None, "Lucifer", "Lucifer is already running for this data directory."
        )
        return 1
    assistant, apps = build(settings)
    window = MainWindow(assistant, apps, settings, background_mode=arguments.background)
    activation_server = listen_for_activation(activation_name, window.show_assistant, window)
    window.show()
    if arguments.background:
        window.hide()
    # Give the desktop audio session time to initialize after login/briefing playback.
    QTimer.singleShot(12000 if arguments.startup else 750, window.start_hands_free)
    if arguments.startup:
        QTimer.singleShot(8000, window.show_startup_briefing)
    result = application.exec()
    activation_server.close()
    lock.unlock()
    return result


if __name__ == "__main__":
    raise SystemExit(main())
