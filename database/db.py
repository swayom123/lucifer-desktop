"""Thread-safe per-operation SQLite connections and private metadata history."""

import os
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path


class Database:
    def __init__(self, path: Path):
        self.path = path
        fd = os.open(path, os.O_CREAT | os.O_WRONLY, 0o600)
        os.close(fd)
        if os.name == "posix":
            path.chmod(0o600)
        with self.connect() as connection:
            connection.execute("""CREATE TABLE IF NOT EXISTS history (
                id INTEGER PRIMARY KEY, time TEXT NOT NULL, command TEXT NOT NULL,
                tool TEXT NOT NULL, code TEXT NOT NULL, ok INTEGER NOT NULL,
                duration_ms INTEGER NOT NULL)""")
            connection.execute("PRAGMA user_version = 1")

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=5)
        connection.row_factory = sqlite3.Row
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def record(self, record: dict) -> None:
        with self.connect() as connection:
            connection.execute(
                """INSERT INTO history(time, command, tool, code, ok, duration_ms)
                VALUES (:time, :command, :tool, :code, :ok, :duration_ms)""",
                record,
            )
            connection.execute(
                "DELETE FROM history WHERE id NOT IN "
                "(SELECT id FROM history ORDER BY id DESC LIMIT 1000)"
            )

    def recent(self, limit: int = 100) -> list[dict]:
        with self.connect() as connection:
            return [
                dict(row)
                for row in connection.execute(
                    "SELECT * FROM history ORDER BY id DESC LIMIT ?", (limit,)
                )
            ]
