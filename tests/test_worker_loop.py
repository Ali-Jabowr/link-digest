from pathlib import Path

import pytest

from link_digest.botmain import _work
from link_digest.pipeline import Digest
from link_digest.queue import JobQueue
from link_digest.telegram import TelegramError

DIGEST = Digest("Title", "Short.", Path("/n/1.md"), Path("/h/1.html"), 3, 0)


class Stop(BaseException):
    """Ends the endless worker loop: no handler in the bot catches it."""


class OutageThenStopSender:
    def __init__(self) -> None:
        self.errors = iter(
            [TelegramError("sendMessage failed: network error", "network"), Stop()]
        )

    def reply(self, chat_id: int, message_id: int, text: str) -> None:
        raise next(self.errors)

    def reply_file(self, chat_id: int, message_id: int, path: Path) -> None:
        raise AssertionError("the summary never went through")


def test_worker_loop_waits_between_tries_during_an_outage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    queue = JobQueue(tmp_path / "queue.db")
    queue.add("https://a.example/1", -100, 7)
    waits: list[float] = []
    monkeypatch.setattr("link_digest.botmain.time.sleep", waits.append)

    with pytest.raises(Stop):
        _work(queue, lambda url: DIGEST, OutageThenStopSender())

    assert waits == [5]
