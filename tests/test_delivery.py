import sqlite3
from collections.abc import Iterator
from contextlib import closing
from pathlib import Path

import pytest

from link_digest.bot import process_next
from link_digest.pipeline import Digest
from link_digest.queue import JobQueue
from link_digest.telegram import TelegramError

URL = "https://a.example/1"
FIRST_DIGEST_DELIVERED = [
    (
        "reply",
        -100,
        7,
        "First\n\nOne.\n\nCitations: 3, unverified: 0\nhttps://a.example/1",
    ),
    ("reply_file", -100, 7, "/h/1.html"),
]


class Killed(BaseException):
    """Stands in for the process dying: no handler in the bot catches it."""


class FakeSender:
    def __init__(self) -> None:
        self.calls: list[tuple[str, int, int, str]] = []

    def reply(self, chat_id: int, message_id: int, text: str) -> None:
        self.calls.append(("reply", chat_id, message_id, text))

    def reply_file(self, chat_id: int, message_id: int, path: Path) -> None:
        self.calls.append(("reply_file", chat_id, message_id, str(path)))


class DownSender(FakeSender):
    def reply(self, chat_id: int, message_id: int, text: str) -> None:
        raise TelegramError("sendMessage failed: HTTP 502")


class KilledSender(FakeSender):
    def reply(self, chat_id: int, message_id: int, text: str) -> None:
        raise Killed


def _digests() -> Iterator[Digest]:
    return iter(
        [
            Digest("First", "One.", Path("/n/1.md"), Path("/h/1.html"), 3, 0),
            Digest("Second", "Two.", Path("/n/2.md"), Path("/h/2.html"), 4, 1),
        ]
    )


def test_retry_after_a_failed_delivery_sends_the_saved_digest(tmp_path: Path) -> None:
    queue = JobQueue(tmp_path / "queue.db")
    queue.add(URL, -100, 7)
    digests = _digests()
    sender = FakeSender()

    process_next(queue, lambda url: next(digests), DownSender())
    process_next(queue, lambda url: next(digests), sender)

    assert sender.calls == FIRST_DIGEST_DELIVERED


def test_digest_finished_before_a_restart_is_delivered_after_it(
    tmp_path: Path,
) -> None:
    path = tmp_path / "queue.db"
    queue = JobQueue(path)
    queue.add(URL, -100, 7)
    digests = _digests()
    sender = FakeSender()

    with pytest.raises(Killed):
        process_next(queue, lambda url: next(digests), KilledSender())
    restarted = JobQueue(path)
    restarted.reset_running()
    process_next(restarted, lambda url: next(digests), sender)

    assert sender.calls == FIRST_DIGEST_DELIVERED


def test_a_database_from_before_saved_digests_keeps_its_jobs_and_saves_them(
    tmp_path: Path,
) -> None:
    path = tmp_path / "queue.db"
    with closing(sqlite3.connect(path)) as conn, conn:
        conn.executescript(
            """
            CREATE TABLE jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                url TEXT NOT NULL UNIQUE,
                chat_id INTEGER NOT NULL,
                message_id INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                attempts INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE meta (key TEXT PRIMARY KEY, value INTEGER NOT NULL);
            INSERT INTO jobs (url, chat_id, message_id)
                VALUES ('https://a.example/1', -100, 7);
            """
        )
    queue = JobQueue(path)
    digests = _digests()
    sender = FakeSender()

    process_next(queue, lambda url: next(digests), DownSender())
    process_next(queue, lambda url: next(digests), sender)

    assert sender.calls == FIRST_DIGEST_DELIVERED
