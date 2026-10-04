"""Home-contained folder operations; resolve symlinks before validating paths."""

import os
import subprocess
from pathlib import Path

from automation.platforms import detect_os
from core.models import Result

FOLDERS = {"home": "", "downloads": "Downloads", "documents": "Documents", "desktop": "Desktop"}


def validate_path(path: Path, root: Path | None = None) -> Path:
    home = (root or Path.home()).resolve()
    resolved = path.expanduser().resolve()
    if not resolved.is_relative_to(home):
        raise ValueError("File access is restricted to your home directory.")
    relative = resolved.relative_to(home)
    blocked = {"AppData", "Library", "Credentials", "Microsoft"}
    if any(part.startswith(".") or part in blocked for part in relative.parts):
        raise ValueError("Access to hidden or credential storage folders is blocked.")
    return resolved


def validate_folder_name(name: str) -> None:
    if (
        len(name) > 120
        or name in {".", ".."}
        or name.startswith(".")
        or any(c in name for c in '/\\<>:"|?*')
        or name[-1:] in {" ", "."}
        or name.split(".")[0].upper()
        in {
            "CON",
            "PRN",
            "AUX",
            "NUL",
            *[f"COM{i}" for i in range(1, 10)],
            *[f"LPT{i}" for i in range(1, 10)],
        }
    ):
        raise ValueError("Use a simple folder name with no path separators or reserved characters.")


def create_folder(name: str) -> Result:
    validate_folder_name(name)
    path = validate_path(Path.home() / name)
    try:
        path.mkdir(mode=0o700)
    except FileExistsError:
        return Result(False, "ALREADY_EXISTS", "A file or folder with that name already exists.")
    return Result(True, "FOLDER_CREATED", f"Created {path}.")


def open_folder(name: str) -> Result:
    if name not in FOLDERS:
        raise ValueError("Choose Home, Downloads, Documents, or Desktop.")
    path = validate_path(Path.home() / FOLDERS[name])
    if not path.is_dir():
        return Result(False, "FOLDER_NOT_FOUND", "That folder does not exist on this computer.")
    system = detect_os()
    if system == "Windows":
        os.startfile(str(path))
    else:
        completed = subprocess.run(
            ["open" if system == "Darwin" else "xdg-open", str(path)],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=15,
            check=False,
        )
        if completed.returncode:
            return Result(False, "OPEN_FAILED", "The file manager could not open the folder.")
    return Result(True, "FOLDER_OPENED", "Folder opened in your file manager.")
