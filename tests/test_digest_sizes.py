import logging
import subprocess
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from link_digest.bot import process_next
from link_digest.citations import Segment
from link_digest.pipeline import Digest, Source
from link_digest.queue import JobQueue
from link_digest.summarize import summarize

SOURCE = Source("https://a.example/1", "video", "", [Segment(5, "private words")])
DIGEST = Digest("Title", "Short.", Path("/n/1.md"), Path("/h/1.html"), 3, 0, "video")


class QuietSender:
    def reply(self, chat_id: int, message_id: int, text: str) -> None:
        pass

    def reply_file(self, chat_id: int, message_id: int, path: Path) -> None:
        pass


def test_summarize_logs_only_the_sizes_of_the_prompt_and_report(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    def fake_run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(command, 0, "secret", "")

    monkeypatch.setattr("link_digest.summarize.build_prompt", lambda source: "12345")
    monkeypatch.setattr("link_digest.summarize.subprocess.run", fake_run)

    with caplog.at_level(logging.INFO, logger="link_digest.summarize"):
        summarize(SOURCE)

    assert caplog.messages == ["claude prompt: 5 chars, report: 6 chars"]


def test_a_successful_digest_logs_its_run_time(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    queue = JobQueue(tmp_path / "queue.db")
    queue.add("https://a.example/1", -100, 7)
    times: Iterator[float] = iter([10.0, 12.5])

    with caplog.at_level(logging.INFO, logger="link_digest.bot"):
        process_next(
            queue,
            lambda url: DIGEST,
            QuietSender(),
            clock=lambda: next(times),
        )

    assert caplog.messages == ["digest of https://a.example/1 took 2.5s"]
