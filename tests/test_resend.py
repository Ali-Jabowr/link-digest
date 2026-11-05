from collections.abc import Iterator
from pathlib import Path

import pytest

from link_digest.bot import process_next
from link_digest.pipeline import Digest, DigestError
from link_digest.queue import Job, JobQueue
from link_digest.telegram import TelegramError

URL = "https://a.example/1"


class RecordingSender:
    def __init__(self) -> None:
        self.calls: list[tuple[str, int, int, str]] = []

    def reply(self, chat_id: int, message_id: int, text: str) -> None:
        self.calls.append(("reply", chat_id, message_id, text))

    def reply_file(self, chat_id: int, message_id: int, path: Path) -> None:
        self.calls.append(("reply_file", chat_id, message_id, str(path)))


class RejectingSender(RecordingSender):
    def reply(self, chat_id: int, message_id: int, text: str) -> None:
        raise TelegramError("sendMessage failed: HTTP 403", "rejected")


def _fails(url: str) -> Digest:
    raise DigestError("fetch", "boom")


def _digests() -> Iterator[Digest]:
    return iter(
        [
            Digest("First", "One.", Path("/n/1.md"), Path("/h/1.html"), 3, 0),
            Digest("Second", "Two.", Path("/n/2.md"), Path("/h/2.html"), 4, 1),
        ]
    )


@pytest.fixture
def queue(tmp_path: Path) -> JobQueue:
    job_queue = JobQueue(tmp_path / "queue.db")
    job_queue.add(URL, -100, 7)
    return job_queue


def test_resending_a_link_that_failed_at_its_digest_queues_it_afresh(
    queue: JobQueue,
) -> None:
    sender = RecordingSender()
    process_next(queue, _fails, sender)
    process_next(queue, _fails, sender)
    process_next(queue, _fails, sender)

    added = queue.add(URL, -100, 105)

    assert added is True
    assert queue.next_job() == Job(1, URL, -100, 105, 0)


def test_resending_a_link_that_failed_at_delivery_delivers_the_saved_digest(
    queue: JobQueue,
) -> None:
    digests = _digests()
    rejecting = RejectingSender()
    process_next(queue, lambda url: next(digests), rejecting)
    process_next(queue, lambda url: next(digests), rejecting)
    process_next(queue, lambda url: next(digests), rejecting)
    sender = RecordingSender()

    added = queue.add(URL, -100, 105)
    process_next(queue, lambda url: next(digests), sender)

    assert added is True
    assert sender.calls == [
        (
            "reply",
            -100,
            105,
            "First\n\nOne.\n\nCitations: 3, unverified: 0\nhttps://a.example/1",
        ),
        ("reply_file", -100, 105, "/h/1.html"),
    ]


def test_resending_a_running_link_is_refused(queue: JobQueue) -> None:
    queue.next_job()

    assert queue.add(URL, -100, 105) is False
