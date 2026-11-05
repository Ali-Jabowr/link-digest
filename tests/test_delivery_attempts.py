from pathlib import Path

from link_digest.bot import process_next
from link_digest.pipeline import Digest, DigestError
from link_digest.queue import JobQueue
from link_digest.telegram import TelegramError

URL = "https://a.example/1"
DIGEST = Digest("Title", "Short.", Path("/n/1.md"), Path("/h/1.html"), 3, 0)


class DownSender:
    def reply(self, chat_id: int, message_id: int, text: str) -> None:
        raise TelegramError("sendMessage failed: HTTP 502")

    def reply_file(self, chat_id: int, message_id: int, path: Path) -> None:
        raise TelegramError("sendDocument failed: HTTP 502")


def _fails(url: str) -> Digest:
    raise DigestError("fetch", "boom")


def test_attempts_at_the_digest_do_not_use_up_tries_at_delivery(
    tmp_path: Path,
) -> None:
    queue = JobQueue(tmp_path / "queue.db")
    queue.add(URL, -100, 7)
    sender = DownSender()

    process_next(queue, _fails, sender)
    process_next(queue, _fails, sender)
    process_next(queue, lambda url: DIGEST, sender)

    job = queue.next_job()
    assert job is not None
    assert job.attempts == 1
