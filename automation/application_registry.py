"""Discover known desktop applications without interpreting shell syntax."""

import configparser
import os
import re
import shlex
import shutil
import subprocess
import threading
from dataclasses import dataclass
from pathlib import Path

from automation.platforms import detect_os
from core.models import Level, Result


@dataclass(frozen=True)
class Application:
    name: str
    aliases: tuple[str, ...]
    linux: tuple[str, ...]
    windows: tuple[str, ...]
    mac: str
    permission: Level = Level.SAFE
    desktop_command: tuple[str, ...] = ()


APPLICATIONS = (
    Application(
        "Visual Studio Code",
        ("vs code", "vscode", "visual studio code", "code"),
        ("code", "code-oss", "codium"),
        ("Code.exe",),
        "Visual Studio Code",
    ),
    Application(
        "Chrome",
        ("chrome", "google chrome"),
        ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser"),
        ("chrome.exe",),
        "Google Chrome",
    ),
    Application("Firefox", ("firefox",), ("firefox",), ("firefox.exe",), "Firefox"),
    Application(
        "Terminal",
        ("terminal",),
        ("x-terminal-emulator", "gnome-terminal", "konsole", "xfce4-terminal"),
        ("wt.exe", "cmd.exe"),
        "Terminal",
        Level.CONFIRM,
    ),
    Application(
        "File Manager",
        ("file manager", "files"),
        ("nautilus", "dolphin", "thunar", "pcmanfm"),
        ("explorer.exe",),
        "Finder",
    ),
    Application("Spotify", ("spotify",), ("spotify",), ("Spotify.exe",), "Spotify"),
    Application(
        "Calculator",
        ("calculator", "calc"),
        ("gnome-calculator", "kcalc", "galculator"),
        ("calc.exe",),
        "Calculator",
    ),
    Application(
        "Settings", ("settings",), ("gnome-control-center", "systemsettings"), (), "System Settings"
    ),
)

WINDOWS_PATHS = {
    "Visual Studio Code": ("Programs/Microsoft VS Code/Code.exe", "Microsoft VS Code/Code.exe"),
    "Chrome": ("Google/Chrome/Application/chrome.exe",),
    "Firefox": ("Mozilla Firefox/firefox.exe",),
    "Spotify": ("Spotify/Spotify.exe",),
}


class ApplicationRegistry:
    def __init__(self, system: str | None = None):
        self.system = system or detect_os()
        self._aliases = {alias: app for app in APPLICATIONS for alias in app.aliases}
        self._applications = list(APPLICATIONS)
        if self.system == "Linux":
            self._load_desktop_entries()

    def resolve(self, name: str) -> Application:
        app = self._aliases.get(name.strip().casefold())
        if app is None:
            raise ValueError(
                "That application is not installed or visible in the application menu."
            )
        return app

    @staticmethod
    def _key(value: str) -> str:
        return re.sub(r"\s+", " ", value.casefold().strip())

    def _load_desktop_entries(self) -> None:
        """Add visible Linux menu applications using their validated Exec fields."""
        roots = [Path.home() / ".local/share/applications"]
        roots.extend(
            Path(item) / "applications"
            for item in os.getenv("XDG_DATA_DIRS", "/usr/local/share:/usr/share").split(":")
            if item
        )
        seen = {self._key(alias) for alias in self._aliases}
        for root in roots:
            if not root.is_dir():
                continue
            for path in sorted(root.glob("*.desktop")):
                entry = configparser.ConfigParser(interpolation=None, strict=False)
                entry.optionxform = str
                try:
                    if path.stat().st_size > 1_000_000:
                        continue
                    entry.read(path, encoding="utf-8")
                    section = entry["Desktop Entry"]
                    if section.get("Type", "Application") != "Application" or section.getboolean(
                        "Hidden", fallback=False
                    ):
                        continue
                    name = section.get("Name", "").strip()
                    command = self._desktop_exec(section.get("Exec", ""))
                    if not name or not command:
                        continue
                    aliases = tuple(dict.fromkeys((self._key(name), self._key(path.stem))))
                    if any(alias in seen for alias in aliases):
                        continue
                    permission = (
                        Level.CONFIRM
                        if section.getboolean("Terminal", fallback=False)
                        or "TerminalEmulator" in section.get("Categories", "")
                        else Level.SAFE
                    )
                    app = Application(name, aliases, (), (), "", permission, command)
                    self._applications.append(app)
                    self._aliases.update({alias: app for alias in aliases})
                    seen.update(aliases)
                except (configparser.Error, OSError, UnicodeError, ValueError):
                    continue

    @staticmethod
    def _desktop_exec(value: str) -> tuple[str, ...]:
        """Parse a desktop Exec field without ever invoking a shell."""
        if not value or any(char in value for char in (";", "|", "&", "`", "$", "<", ">")):
            return ()
        try:
            tokens = shlex.split(value, posix=True)
        except ValueError:
            return ()
        tokens = [token for token in tokens if not token.startswith("%")]
        if not tokens or any("%" in token for token in tokens):
            return ()
        executable = shutil.which(tokens[0])
        if executable is None:
            candidate = Path(tokens[0]).expanduser()
            if (
                not candidate.is_absolute()
                or not candidate.is_file()
                or not os.access(candidate, os.X_OK)
            ):
                return ()
            executable = str(candidate)
        return (executable, *tokens[1:])

    def command(self, app: Application) -> list[str] | None:
        if self.system == "Darwin":
            for base in (
                Path("/Applications"),
                Path("/System/Applications"),
                Path("/System/Applications/Utilities"),
                Path.home() / "Applications",
                Path("/System/Library/CoreServices"),
            ):
                bundle = base / f"{app.mac}.app"
                if bundle.is_dir():
                    return ["/usr/bin/open", "-a", str(bundle)]
            return None
        if self.system == "Windows" and app.name == "Settings":
            return ["@windows-settings"]
        if app.desktop_command:
            return list(app.desktop_command)
        candidates = app.linux if self.system == "Linux" else app.windows
        for candidate in candidates:
            executable = shutil.which(candidate)
            if executable:
                return [executable]
        if self.system == "Linux":
            for candidate in candidates:
                snap = Path("/snap/bin") / candidate
                if snap.is_file() and os.access(snap, os.X_OK):
                    return [str(snap)]
        if self.system == "Windows":
            for root in ("LOCALAPPDATA", "APPDATA", "ProgramFiles", "ProgramFiles(x86)"):
                if not os.getenv(root):
                    continue
                for relative in WINDOWS_PATHS.get(app.name, ()):
                    path = Path(os.environ[root]) / relative
                    if path.is_file():
                        return [str(path)]
        return None

    def level(self, arguments: dict) -> Level:
        return self.resolve(arguments["app_name"]).permission

    def discover(self) -> list[dict]:
        return [
            {
                "name": app.name,
                "aliases": ", ".join(app.aliases),
                "installed": self.command(app) is not None,
                "level": app.permission.value,
            }
            for app in self._applications
        ]

    def launch(self, app_name: str) -> Result:
        app = self.resolve(app_name)
        command = self.command(app)
        if command is None:
            return Result(
                False,
                "APP_NOT_INSTALLED",
                f"{app.name} doesn't appear to be installed on this computer.",
            )
        try:
            if command == ["@windows-settings"]:
                os.startfile("ms-settings:")
            else:
                # No caller-controlled argv and no shell, even for terminal applications.
                process = subprocess.Popen(
                    command,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    start_new_session=self.system != "Windows",
                )
                try:
                    code = process.wait(timeout=0.4)
                    if code != 0:
                        return Result(False, "LAUNCH_FAILED", f"{app.name} could not be launched.")
                except subprocess.TimeoutExpired:
                    threading.Thread(target=process.wait, daemon=True).start()
            return Result(True, "LAUNCH_REQUESTED", f"Launch requested for {app.name}.")
        except OSError:
            return Result(False, "LAUNCH_FAILED", f"{app.name} could not be launched.")
