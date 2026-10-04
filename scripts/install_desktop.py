"""Install Lucifer in the current Linux user's applications menu."""

import os
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]


def desktop_exec_arg(path: Path) -> str:
    value = str(path)
    if any(character in value for character in "\r\n\0"):
        raise ValueError("Launcher paths must not contain control characters.")
    value = value.replace("%", "%%")
    for character in ("\\", '"', "$", "`"):
        value = value.replace(character, "\\" + character)
    return f'"{value}"'


def desktop_entry(project: Path = PROJECT) -> str:
    python = project / ".venv/bin/python"
    main = project / "main.py"
    icon = project / "assets/lucifer.svg"
    return (
        "[Desktop Entry]\n"
        "Version=1.0\n"
        "Type=Application\n"
        "Name=Lucifer\n"
        "Comment=Voice and desktop assistant\n"
        f"Exec={desktop_exec_arg(python)} {desktop_exec_arg(main)}\n"
        f"TryExec={python}\n"
        f"Path={project}\n"
        f"Icon={icon}\n"
        "Terminal=false\n"
        "StartupNotify=true\n"
        "Categories=Utility;\n"
        "Keywords=assistant;voice;desktop;\n"
    )


def main() -> int:
    if sys.platform != "linux":
        print("This applications-menu installer supports Linux desktops.", file=sys.stderr)
        return 1
    python = PROJECT / ".venv/bin/python"
    if not python.is_file():
        print(f"Install dependencies into {PROJECT / '.venv'} first.", file=sys.stderr)
        return 1
    data_home = Path(os.getenv("XDG_DATA_HOME") or Path.home() / ".local/share")
    applications = data_home / "applications"
    applications.mkdir(parents=True, exist_ok=True)
    target = applications / "lucifer.desktop"
    target.write_text(desktop_entry(), encoding="utf-8")
    target.chmod(0o644)
    print(f"Installed {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
