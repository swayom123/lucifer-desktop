"""Persist metadata, never user text, tool argument values or exception details."""

import json
import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path


def create_logger(directory: Path) -> logging.Logger:
    logger = logging.getLogger(f"lucifer.{directory}")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    if not logger.handlers:
        path = directory / "actions.jsonl"
        fd = os.open(path, os.O_CREAT | os.O_APPEND | os.O_WRONLY, 0o600)
        os.close(fd)
        if os.name == "posix":
            path.chmod(0o600)
        handler = RotatingFileHandler(path, maxBytes=1_000_000, backupCount=3)
        handler.setFormatter(logging.Formatter("%(message)s"))
        logger.addHandler(handler)
    return logger


def log_action(logger: logging.Logger, record: dict) -> None:
    logger.info(json.dumps(record, separators=(",", ":")))


def read_log_tail(path: Path, limit: int = 30_000) -> str:
    """Read only the visible tail of a bounded log instead of loading the whole file."""
    if limit <= 0 or not path.exists():
        return ""
    with path.open("rb") as stream:
        stream.seek(0, os.SEEK_END)
        size = stream.tell()
        stream.seek(max(0, size - limit))
        return stream.read(limit).decode("utf-8", errors="replace")
