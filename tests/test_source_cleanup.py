from collections.abc import Callable
from datetime import date
from pathlib import Path

import pytest
from test_pipeline import REPORT, SOURCE

from link_digest.bot import process_next
from link_digest.botmain import _work
from link_digest.citations import Segment
from link_digest.pipeline import (
    Digest,
    DigestError,
    Source,
    digest_reusing_source,
    forget_source,
)
from link_digest.queue import JobQueue

URL = "https://example.com/v"
TODAY = date(2026, 11, 5)
ARTICLE = Source(URL, "article", "the post around it", [Segment(1, "héllo")])


class Stop(BaseException):
    """Ends the endless worker loop: no handler in the bot catches it."""


class QuietSender:
    def reply(self, chat_id: int, message_id: int, text: str) -> None:
        pass

    def reply_file(self, chat_id: int, message_id: int, path: Path) -> None:
        pass


def _failing_summarize(source: Source) -> str:
    raise RuntimeError("claude failed")


def _run(sources: Path, notes: Path) -> Callable[[str], Digest]:
    def run(url: str) -> Digest:
        return digest_reusing_source(
            url, lambda _url: SOURCE, _failing_summarize, notes, notes, sources, TODAY
        )

    return run


def test_a_link_that_gives_up_leaves_no_saved_source(tmp_path: Path) -> None:
    sources = tmp_path / "sources"
    queue = JobQueue(tmp_path / "queue.db")
    queue.add(URL, -100, 7)
    run = _run(sources, tmp_path)

    process_next(queue, run, QuietSender(), forget=lambda u: forget_source(u, sources))
    process_next(queue, run, QuietSender(), forget=lambda u: forget_source(u, sources))
    process_next(queue, run, QuietSender(), forget=lambda u: forget_source(u, sources))

    assert list(sources.iterdir()) == []


def test_a_link_still_being_retried_keeps_its_saved_source(tmp_path: Path) -> None:
    sources = tmp_path / "sources"
    queue = JobQueue(tmp_path / "queue.db")
    queue.add(URL, -100, 7)
    run = _run(sources, tmp_path)

    process_next(queue, run, QuietSender(), forget=lambda u: forget_source(u, sources))

    assert len(list(sources.iterdir())) == 1


def test_the_worker_forgets_the_source_of_a_link_that_gives_up(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def stop(_seconds: float) -> None:
        raise Stop

    def always_fails(url: str) -> Digest:
        raise DigestError("summarize", "claude failed")

    queue = JobQueue(tmp_path / "queue.db")
    queue.add(URL, -100, 7)
    forgotten: list[str] = []
    monkeypatch.setattr("link_digest.botmain.time.sleep", stop)

    with pytest.raises(Stop):
        _work(queue, always_fails, QuietSender(), forgotten.append)

    assert forgotten == [URL]


def test_an_unusable_sources_directory_does_not_stop_a_digest(tmp_path: Path) -> None:
    not_a_directory = tmp_path / "sources"
    not_a_directory.write_text("in the way", encoding="utf-8")

    result = digest_reusing_source(
        URL,
        lambda _url: SOURCE,
        lambda _source: REPORT,
        tmp_path,
        tmp_path,
        not_a_directory,
        TODAY,
    )

    assert result.title == "Bee Talk"


def test_a_reused_source_keeps_every_field(tmp_path: Path) -> None:
    sources = tmp_path / "sources"
    seen: list[Source] = []

    def record_and_fail(source: Source) -> str:
        seen.append(source)
        raise RuntimeError("claude failed")

    def attempt() -> None:
        digest_reusing_source(
            URL,
            lambda _url: ARTICLE,
            record_and_fail,
            tmp_path,
            tmp_path,
            sources,
            TODAY,
        )

    with pytest.raises(DigestError):
        attempt()
    with pytest.raises(DigestError):
        attempt()

    assert seen == [ARTICLE, ARTICLE]
