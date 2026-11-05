from pathlib import Path
from typing import NoReturn

from link_digest.bot import process_next
from link_digest.pipeline import Digest, DigestError
from link_digest.queue import JobQueue

DIGEST = Digest("T", "S", Path("/n/1.md"), Path("/h/1.html"), 1, 0, "video")


class QuietSender:
    def reply(self, chat_id: int, message_id: int, text: str) -> None:
        pass

    def reply_file(self, chat_id: int, message_id: int, path: Path) -> None:
        pass


def test_a_failed_run_records_nothing(tmp_path: Path) -> None:
    queue = JobQueue(tmp_path / "queue.db")
    queue.add("https://a.example/1", 10, 100)

    def fails(_url: str) -> NoReturn:
        raise DigestError("fetch", "down")

    process_next(queue, fails, QuietSender())

    assert queue.run_seconds("video") == []


def test_delivering_a_saved_digest_records_nothing(tmp_path: Path) -> None:
    queue = JobQueue(tmp_path / "queue.db")
    queue.add("https://a.example/1", 10, 100)
    job = queue.next_job()
    assert job is not None
    queue.save_digest(job.id, DIGEST)
    queue.retry_delivery(job.id)

    process_next(queue, lambda _url: DIGEST, QuietSender())

    assert queue.run_seconds("video") == []
    # A Digest saved before kinds were kept loads with kind "".
    assert queue.run_seconds("") == []
