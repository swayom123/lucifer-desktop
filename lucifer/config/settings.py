"""Validated settings for the new API and CLI."""

import os
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field


class Settings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    database_path: Path
    log_level: str = Field(default="INFO", pattern=r"^(DEBUG|INFO|WARNING|ERROR)$")

    @classmethod
    def load(cls, env_file: Path | None = None) -> "Settings":
        source = env_file or Path(__file__).resolve().parents[2] / ".env"
        if source.is_file():
            load_dotenv(source, override=False)
        data_dir = Path(os.environ.get("LUCIFER_DATA_DIR", "~/.local/share/lucifer"))
        default_path = data_dir.expanduser() / "foundation.db"
        return cls(
            database_path=Path(os.environ.get("LUCIFER_FOUNDATION_DB") or str(default_path))
            .expanduser()
            .resolve(),
            log_level=os.environ.get("LUCIFER_LOG_LEVEL", "INFO").upper(),
        )
