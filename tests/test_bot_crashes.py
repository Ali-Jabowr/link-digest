import threading
from pathlib import Path

import pytest

from link_digest.bot import process_next
from link_digest.botmain import run_until_worker_dies
from link_digest.pipeline import Digest
from link_digest.queue import JobQueue


class FakeSender:
    def reply(self, chat_id: int, message_id: int, text: str) -> None:
        pass

    def reply_file(self, chat_id: int, message_id: int, path: Path) -> None:
        raise FileNotFoundError(path)


def _crash(_url: str) -> Digest:
    raise TypeError("library bug")


def _good(_url: str) -> Digest:
    return Digest("T", "S", Path("/x.md"), Path("/missing.html"), 1, 0)


def test_unexpected_error_counts_an_attempt_and_is_not_swallowed(
    tmp_path: Path,
) -> None:
    queue = JobQueue(tmp_path / "q.db")
    queue.add("https://example.com/a", 1, 2)
    with pytest.raises(TypeError, match="library bug"):
        process_next(queue, _crash, FakeSender())
    job = queue.next_job()
    assert job is not None
    assert job.attempts == 1


def test_unreadable_report_file_counts_an_attempt_and_is_not_swallowed(
    tmp_path: Path,
) -> None:
    queue = JobQueue(tmp_path / "q.db")
    queue.add("https://example.com/a", 1, 2)
    with pytest.raises(FileNotFoundError):
        process_next(queue, _good, FakeSender())
    job = queue.next_job()
    assert job is not None
    assert job.attempts == 1


def test_bot_exits_with_failure_when_the_worker_has_died() -> None:
    worker = threading.Thread(target=lambda: None)
    worker.start()
    worker.join()
    assert run_until_worker_dies(worker, lambda: None) == 1
