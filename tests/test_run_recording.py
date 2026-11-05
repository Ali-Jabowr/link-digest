from pathlib import Path

from link_digest.bot import process_next
from link_digest.pipeline import Digest
from link_digest.queue import JobQueue

DIGEST = Digest("T", "S", Path("/n/1.md"), Path("/h/1.html"), 1, 0, "video")


class QuietSender:
    def reply(self, chat_id: int, message_id: int, text: str) -> None:
        pass

    def reply_file(self, chat_id: int, message_id: int, path: Path) -> None:
        pass


def test_a_successful_run_records_its_time_under_the_kind_of_source(
    tmp_path: Path,
) -> None:
    queue = JobQueue(tmp_path / "queue.db")
    queue.add("https://a.example/1", 10, 100)
    times = iter([100.0, 130.0])

    process_next(queue, lambda _url: DIGEST, QuietSender(), clock=lambda: next(times))

    assert queue.run_seconds("video") == [30.0]
