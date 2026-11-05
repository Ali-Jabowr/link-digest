"""A small sqlite job queue shared by the Telegram poller and the worker thread."""

import json
import sqlite3
from collections.abc import Iterator
from contextlib import closing, contextmanager
from dataclasses import dataclass
from pathlib import Path

from link_digest.pipeline import Digest

_MAX_ATTEMPTS = 3
_ADDED_COLUMNS = {
    "digest": "TEXT",
    "summary_sent": "INTEGER NOT NULL DEFAULT 0",
    "kind": "TEXT",
    "run_seconds": "REAL",
}

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
    digest: Digest | None = None  # set once the Digest is finished
    summary_sent: bool = False


class JobQueue:
    """Every method opens its own connection: sqlite connections are per-thread."""

    def __init__(self, path: Path) -> None:
        self._path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(_SCHEMA)
            columns = {row[1] for row in conn.execute("PRAGMA table_info(jobs)")}
            for name, definition in _ADDED_COLUMNS.items():
                if name not in columns:
                    conn.execute(f"ALTER TABLE jobs ADD COLUMN {name} {definition}")

    def add(self, url: str, chat_id: int, message_id: int) -> bool:
        """Queue a URL, or requeue it if it failed. False if it is already known."""
        with self._connect() as conn:
            cursor = conn.execute(
                "INSERT INTO jobs (url, chat_id, message_id) VALUES (?, ?, ?) "
                "ON CONFLICT(url) DO UPDATE SET status = 'pending', attempts = 0, "
                "chat_id = excluded.chat_id, message_id = excluded.message_id "
                "WHERE status = 'failed'",
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
                "RETURNING id, url, chat_id, message_id, attempts, digest, summary_sent"
            ).fetchone()
        if row is None:
            return None
        job_id, url, chat_id, message_id, attempts, digest, summary_sent = row
        return Job(
            job_id,
            url,
            chat_id,
            message_id,
            attempts,
            _load_digest(digest),
            bool(summary_sent),
        )

    def save_digest(self, job_id: int, digest: Digest) -> None:
        """Save a finished Digest. Attempts now count tries at its Delivery."""
        with self._connect() as conn:
            conn.execute(
                "UPDATE jobs SET digest = ?, attempts = 0 WHERE id = ?",
                (_dump_digest(digest), job_id),
            )

    def record_run(self, job_id: int, kind: str, seconds: float) -> None:
        """Remember how long a job's Digest took and the kind of its Source."""
        with self._connect() as conn:
            conn.execute(
                "UPDATE jobs SET kind = ?, run_seconds = ? WHERE id = ?",
                (kind, seconds, job_id),
            )

    def run_seconds(self, kind: str) -> list[float]:
        """Return the recorded times for a kind of Source, oldest job first."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT run_seconds FROM jobs "
                "WHERE kind = ? AND run_seconds IS NOT NULL ORDER BY id",
                (kind,),
            ).fetchall()
        return [row[0] for row in rows]

    def mark_summary_sent(self, job_id: int) -> None:
        with self._connect() as conn:
            conn.execute("UPDATE jobs SET summary_sent = 1 WHERE id = ?", (job_id,))

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

    def retry_delivery(self, job_id: int) -> None:
        """Count a try that hit an outage. Unlike fail, this never gives up."""
        with self._connect() as conn:
            conn.execute(
                "UPDATE jobs SET attempts = attempts + 1, status = 'pending' "
                "WHERE id = ?",
                (job_id,),
            )

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


def _dump_digest(digest: Digest) -> str:
    return json.dumps(
        {
            "title": digest.title,
            "summary": digest.summary,
            "markdown_path": str(digest.markdown_path),
            "html_path": str(digest.html_path),
            "citations": digest.citations,
            "unverified": digest.unverified,
        }
    )


def _load_digest(saved: str | None) -> Digest | None:
    if saved is None:
        return None
    fields = json.loads(saved)
    return Digest(
        fields["title"],
        fields["summary"],
        Path(fields["markdown_path"]),
        Path(fields["html_path"]),
        fields["citations"],
        fields["unverified"],
    )
