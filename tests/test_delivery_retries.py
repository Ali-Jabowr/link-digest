import logging
from pathlib import Path

import pytest

from link_digest.bot import process_next
from link_digest.pipeline import Digest
from link_digest.queue import JobQueue
from link_digest.telegram import ErrorKind, TelegramError

URL = "https://a.example/1"
DIGEST = Digest("Title", "Short.", Path("/n/1.md"), Path("/h/1.html"), 3, 0)


class FailingSender:
    def __init__(self, kind: ErrorKind, retry_after: int | None = None) -> None:
        self.error = TelegramError("sendMessage failed: boom", kind, retry_after)

    def reply(self, chat_id: int, message_id: int, text: str) -> None:
        raise self.error

    def reply_file(self, chat_id: int, message_id: int, path: Path) -> None:
        raise self.error


@pytest.fixture
def queue(tmp_path: Path) -> JobQueue:
    job_queue = JobQueue(tmp_path / "queue.db")
    job_queue.add(URL, -100, 7)
    return job_queue


def test_network_errors_never_give_up_and_back_off_up_to_five_minutes(
    queue: JobQueue,
) -> None:
    sender = FailingSender("network")
    waits: list[float] = []

    process_next(queue, lambda url: DIGEST, sender, waits.append)
    process_next(queue, lambda url: DIGEST, sender, waits.append)
    process_next(queue, lambda url: DIGEST, sender, waits.append)
    process_next(queue, lambda url: DIGEST, sender, waits.append)
    process_next(queue, lambda url: DIGEST, sender, waits.append)
    process_next(queue, lambda url: DIGEST, sender, waits.append)
    process_next(queue, lambda url: DIGEST, sender, waits.append)
    process_next(queue, lambda url: DIGEST, sender, waits.append)

    assert waits == [5, 10, 20, 40, 80, 160, 300, 300]
    job = queue.next_job()
    assert job is not None
    assert job.attempts == 8


def test_rate_limit_waits_the_requested_time_without_giving_up(
    queue: JobQueue,
) -> None:
    sender = FailingSender("rate_limited", 37)
    waits: list[float] = []

    process_next(queue, lambda url: DIGEST, sender, waits.append)
    process_next(queue, lambda url: DIGEST, sender, waits.append)
    process_next(queue, lambda url: DIGEST, sender, waits.append)
    process_next(queue, lambda url: DIGEST, sender, waits.append)

    assert waits == [37, 37, 37, 37]
    assert queue.next_job() is not None


def test_rate_limit_without_a_requested_time_backs_off(queue: JobQueue) -> None:
    waits: list[float] = []

    process_next(queue, lambda url: DIGEST, FailingSender("rate_limited"), waits.append)

    assert waits == [5]


def test_rejection_gives_up_after_three_tries_and_logs_why(
    queue: JobQueue, caplog: pytest.LogCaptureFixture
) -> None:
    sender = FailingSender("rejected")
    waits: list[float] = []

    with caplog.at_level(logging.ERROR):
        process_next(queue, lambda url: DIGEST, sender, waits.append)
        process_next(queue, lambda url: DIGEST, sender, waits.append)
        process_next(queue, lambda url: DIGEST, sender, waits.append)

    assert queue.next_job() is None
    assert waits == []
    assert caplog.messages == [
        (
            "gave up delivering https://a.example/1: sendMessage failed: boom; "
            "the report stays at /h/1.html"
        )
    ]


def test_report_file_is_left_on_disk_when_delivery_gives_up(
    queue: JobQueue, tmp_path: Path
) -> None:
    report = tmp_path / "report.html"
    report.write_text("<html>report</html>", encoding="utf-8")
    digest = Digest("Title", "Short.", tmp_path / "r.md", report, 3, 0)
    sender = FailingSender("rejected")

    process_next(queue, lambda url: digest, sender)
    process_next(queue, lambda url: digest, sender)
    process_next(queue, lambda url: digest, sender)

    assert report.read_text(encoding="utf-8") == "<html>report</html>"
