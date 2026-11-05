from pathlib import Path

import pytest

from link_digest.bot import process_next
from link_digest.pipeline import Digest
from link_digest.queue import JobQueue
from link_digest.telegram import TelegramError

URL = "https://a.example/1"
DIGEST = Digest("Title", "Short.", Path("/n/1.md"), Path("/h/1.html"), 3, 0)


class FileDownSender:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def reply(self, chat_id: int, message_id: int, text: str) -> None:
        self.calls.append("reply")

    def reply_file(self, chat_id: int, message_id: int, path: Path) -> None:
        raise TelegramError("sendDocument failed: HTTP 502")


class WorkingSender(FileDownSender):
    def reply_file(self, chat_id: int, message_id: int, path: Path) -> None:
        self.calls.append("reply_file")


@pytest.fixture
def queue(tmp_path: Path) -> JobQueue:
    return JobQueue(tmp_path / "queue.db")


def test_retry_sends_only_the_file_when_the_summary_went_through(
    queue: JobQueue,
) -> None:
    queue.add(URL, -100, 7)
    retry = WorkingSender()

    process_next(queue, lambda url: DIGEST, FileDownSender())
    process_next(queue, lambda url: DIGEST, retry)

    assert retry.calls == ["reply_file"]


def test_summary_went_through_survives_a_restart(tmp_path: Path) -> None:
    path = tmp_path / "queue.db"
    queue = JobQueue(path)
    queue.add(URL, -100, 7)
    retry = WorkingSender()

    process_next(queue, lambda url: DIGEST, FileDownSender())
    process_next(JobQueue(path), lambda url: DIGEST, retry)

    assert retry.calls == ["reply_file"]
