from pathlib import Path
from typing import Any

import pytest

from link_digest.bot import extract_links, format_summary, handle_update, process_next
from link_digest.pipeline import Digest, DigestError
from link_digest.queue import JobQueue
from link_digest.telegram import TelegramError

URL = "https://a.example/1"


def _digest(summary: str = "It is short.") -> Digest:
    return Digest(
        "A Title",
        summary,
        Path("/notes/a.md"),
        Path("/html/a.html"),
        12,
        2,
    )


def _update(chat_id: int, **message: Any) -> dict[str, Any]:
    return {
        "update_id": 5,
        "message": {"message_id": 7, "chat": {"id": chat_id}, **message},
    }


@pytest.fixture
def queue(tmp_path: Path) -> JobQueue:
    return JobQueue(tmp_path / "queue.db")


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


def _fails(url: str) -> Digest:
    raise DigestError("fetch", "boom")


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("look https://a.example/x now", ["https://a.example/x"]),
        ("no links here", []),
        ("ftp://a.example/x", []),
        (
            "http://a.example/a https://b.example/b",
            ["http://a.example/a", "https://b.example/b"],
        ),
        ("https://a.example/x and again https://a.example/x", ["https://a.example/x"]),
        ("(see https://a.example/x).", ["https://a.example/x"]),
        (
            "https://a.example/x, https://b.example/y!",
            ["https://a.example/x", "https://b.example/y"],
        ),
        ("https://a.example/x?v=1&t=2", ["https://a.example/x?v=1&t=2"]),
        ("https://x.com/a/status/1?s=35&t=abc", ["https://x.com/a/status/1"]),
        (
            "https://x.com/a/status/1?s=35&t=abc https://x.com/a/status/1",
            ["https://x.com/a/status/1"],
        ),
        ("https://twitter.com/a/status/1?s=20", ["https://twitter.com/a/status/1"]),
        ("https://x.com/a?s=20", ["https://x.com/a?s=20"]),
    ],
)
def test_extract_links(text: str, expected: list[str]) -> None:
    assert extract_links(text) == expected


def test_handle_update_queues_a_link_from_the_allowed_chat(queue: JobQueue) -> None:
    added = handle_update(_update(-100, text=f"watch {URL}"), -100, queue)

    assert added == [(URL, 7)]
    job = queue.next_job()
    assert job is not None
    assert (job.url, job.chat_id, job.message_id) == (URL, -100, 7)


def test_handle_update_ignores_another_chat(queue: JobQueue) -> None:
    added = handle_update(_update(-999, text=URL), -100, queue)

    assert added == []
    assert queue.next_job() is None


def test_handle_update_ignores_an_update_without_a_message(queue: JobQueue) -> None:
    assert handle_update({"update_id": 5, "edited_message": {}}, -100, queue) == []


def test_handle_update_reads_the_caption(queue: JobQueue) -> None:
    added = handle_update(_update(-100, caption=f"from a photo {URL}"), -100, queue)

    assert added == [(URL, 7)]


def test_handle_update_queues_a_repeated_link_once(queue: JobQueue) -> None:
    first = handle_update(_update(-100, text=URL), -100, queue)
    again = handle_update(_update(-100, text=URL), -100, queue)

    assert first == [(URL, 7)]
    assert again == []


def test_format_summary_exact_output_for_a_small_case() -> None:
    text = format_summary(_digest(), URL)

    assert text == (
        "A Title\n\nIt is short.\n\nCitations: 12, unverified: 2\nhttps://a.example/1"
    )


def test_format_summary_cuts_a_long_summary_but_keeps_url_and_counts() -> None:
    text = format_summary(_digest("word " * 2000), URL)

    assert len(text) <= 4000
    assert text.endswith("\n\nCitations: 12, unverified: 2\nhttps://a.example/1")
    assert text.startswith("A Title\n\nword word")


def test_process_next_returns_false_without_a_job(queue: JobQueue) -> None:
    sender = FakeSender()

    assert process_next(queue, lambda url: _digest(), sender) is False
    assert sender.calls == []


def test_process_next_replies_with_summary_then_file_then_completes(
    queue: JobQueue,
) -> None:
    queue.add(URL, -100, 7)
    sender = FakeSender()

    done = process_next(queue, lambda url: _digest(), sender)

    assert done is True
    assert sender.calls == [
        (
            "reply",
            -100,
            7,
            "A Title\n\nIt is short.\n\nCitations: 12, unverified: 2\n" + URL,
        ),
        ("reply_file", -100, 7, "/html/a.html"),
    ]
    queue.reset_running()
    assert queue.next_job() is None


def test_process_next_retries_quietly_after_a_digest_error(queue: JobQueue) -> None:
    queue.add(URL, -100, 7)
    sender = FakeSender()

    process_next(queue, _fails, sender)

    assert sender.calls == []
    job = queue.next_job()
    assert job is not None
    assert job.attempts == 1


def test_process_next_reports_the_error_on_the_final_attempt(queue: JobQueue) -> None:
    queue.add(URL, -100, 7)
    sender = FakeSender()

    process_next(queue, _fails, sender)
    process_next(queue, _fails, sender)
    assert sender.calls == []
    process_next(queue, _fails, sender)

    assert sender.calls == [
        ("reply", -100, 7, "Could not process https://a.example/1: fetch: boom")
    ]
    assert queue.next_job() is None


def test_process_next_retries_when_delivery_fails(queue: JobQueue) -> None:
    queue.add(URL, -100, 7)

    done = process_next(queue, lambda url: _digest(), DownSender())

    assert done is True
    job = queue.next_job()
    assert job is not None
    assert job.attempts == 1


def test_process_next_survives_a_failed_error_notice(queue: JobQueue) -> None:
    queue.add(URL, -100, 7)
    sender = DownSender()

    process_next(queue, _fails, sender)
    process_next(queue, _fails, sender)
    done = process_next(queue, _fails, sender)

    assert done is True
    assert queue.next_job() is None
