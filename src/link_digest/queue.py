"""A small sqlite job queue shared by the Telegram poller and the worker thread."""

import sqlite3
from collections.abc import Iterator
from contextlib import closing, contextmanager
from dataclasses import dataclass
from pathlib import Path

_MAX_ATTEMPTS = 3

_SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    url TEXT NOT NULL UNIQUE,
    chat_id INTEGER NOT NULL,
    message_id INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    attempts INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value INTEGER NOT NULL);
"""


@dataclass(frozen=True)
class Job:
    id: int
    url: str
    chat_id: int
    message_id: int
    attempts: int


class JobQueue:
    """Every method opens its own connection: sqlite connections are per-thread."""

    def __init__(self, path: Path) -> None:
        self._path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(_SCHEMA)

    def add(self, url: str, chat_id: int, message_id: int) -> bool:
        """Queue a URL. False if it was ever queued before, whatever its state."""
        with self._connect() as conn:
            cursor = conn.execute(
                "INSERT OR IGNORE INTO jobs (url, chat_id, message_id) "
                "VALUES (?, ?, ?)",
                (url, chat_id, message_id),
            )
            return cursor.rowcount == 1

    def next_job(self) -> Job | None:
        """Take the oldest pending job and mark it running."""
        # One UPDATE ... RETURNING so two callers can never claim the same job.
        with self._connect() as conn:
            row = conn.execute(
                "UPDATE jobs SET status = 'running' WHERE id = "
                "(SELECT id FROM jobs WHERE status = 'pending' ORDER BY id LIMIT 1) "
                "RETURNING id, url, chat_id, message_id, attempts"
            ).fetchone()
        return None if row is None else Job(*row)

    def complete(self, job_id: int) -> None:
        with self._connect() as conn:
            conn.execute("UPDATE jobs SET status = 'done' WHERE id = ?", (job_id,))

    def fail(self, job_id: int) -> bool:
        """Count an attempt. True if the job will be retried, False if it gave up."""
        with self._connect() as conn:
            row = conn.execute(
                "UPDATE jobs SET attempts = attempts + 1, "
                "status = CASE WHEN attempts + 1 < ? THEN 'pending' ELSE 'failed' END "
                "WHERE id = ? RETURNING status",
                (_MAX_ATTEMPTS, job_id),
            ).fetchone()
        return row is not None and row[0] == "pending"

    def reset_running(self) -> None:
        """Put jobs left running by a crash back to pending."""
        with self._connect() as conn:
            conn.execute("UPDATE jobs SET status = 'pending' WHERE status = 'running'")

    def get_offset(self) -> int:
        with self._connect() as conn:
            row = conn.execute("SELECT value FROM meta WHERE key = 'offset'").fetchone()
        return 0 if row is None else int(row[0])

    def set_offset(self, offset: int) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO meta (key, value) VALUES ('offset', ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (offset,),
            )

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        # Inner `with conn` commits or rolls back; closing() releases the file.
        with closing(sqlite3.connect(self._path)) as conn, conn:
            yield conn
