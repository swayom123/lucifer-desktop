"""Configuration; .env is read only from the project root."""

import os
import sys
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    wake_word: str = "lucifer"

    @classmethod
    def load(cls) -> "Settings":
        load_dotenv(ROOT / ".env")
        if sys.platform == "win32":
            base = Path(os.getenv("LOCALAPPDATA", str(Path.home() / "AppData/Local")))
        elif sys.platform == "darwin":
            base = Path.home() / "Library/Application Support"
        else:
            base = Path(os.getenv("XDG_DATA_HOME", str(Path.home() / ".local/share")))
        path = Path(os.getenv("LUCIFER_DATA_DIR") or base / "lucifer").expanduser().resolve()
        path.mkdir(parents=True, exist_ok=True, mode=0o700)
        if os.name == "posix":
            path.chmod(0o700)
        wake_word = os.getenv("WAKE_WORD", "lucifer").strip() or "lucifer"
        if len(wake_word) > 40 or any(ord(character) < 32 for character in wake_word):
            wake_word = "lucifer"
        return cls(path, wake_word)
