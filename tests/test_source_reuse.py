from collections.abc import Callable, Iterator
from datetime import date
from pathlib import Path

import pytest
from test_pipeline import REPORT, SOURCE

from link_digest.botmain import _runner
from link_digest.citations import Segment
from link_digest.pipeline import DigestError, Source, digest_reusing_source

URL = "https://example.com/v"
OTHER_URL = "https://example.com/other"
OTHER_SOURCE = Source(URL, "video", "", [Segment(1, "something else")])
TODAY = date(2026, 11, 5)


def _fetcher() -> Callable[[str], Source]:
    sources: Iterator[Source] = iter([SOURCE, OTHER_SOURCE])
    return lambda url: next(sources)


def _summarizer(seen: list[Source], *outcomes: str) -> Callable[[Source], str]:
    """Record each Source, then fail on "fail" or return the given report."""
    remaining = iter(outcomes)

    def summarize(source: Source) -> str:
        seen.append(source)
        outcome = next(remaining)
        if outcome == "fail":
            raise RuntimeError("claude failed")
        return outcome

    return summarize


def _corrupt_saved_sources(directory: Path) -> None:
    for path in directory.iterdir():
        path.write_text("not json", encoding="utf-8")


def test_retry_after_a_summarize_failure_reuses_the_source(tmp_path: Path) -> None:
    seen: list[Source] = []
    fetch = _fetcher()
    summarize = _summarizer(seen, "fail", REPORT)
    sources = tmp_path / "sources"

    with pytest.raises(DigestError):
        digest_reusing_source(URL, fetch, summarize, tmp_path, tmp_path, sources, TODAY)
    digest_reusing_source(URL, fetch, summarize, tmp_path, tmp_path, sources, TODAY)

    assert seen == [SOURCE, SOURCE]


def test_saved_source_is_removed_once_the_digest_is_finished(tmp_path: Path) -> None:
    seen: list[Source] = []
    fetch = _fetcher()
    summarize = _summarizer(seen, "fail", REPORT)
    sources = tmp_path / "sources"

    with pytest.raises(DigestError):
        digest_reusing_source(URL, fetch, summarize, tmp_path, tmp_path, sources, TODAY)
    digest_reusing_source(URL, fetch, summarize, tmp_path, tmp_path, sources, TODAY)

    assert list(sources.iterdir()) == []


def test_a_source_is_not_reused_for_another_link(tmp_path: Path) -> None:
    seen: list[Source] = []
    fetch = _fetcher()
    summarize = _summarizer(seen, "fail", "fail")
    sources = tmp_path / "sources"

    with pytest.raises(DigestError):
        digest_reusing_source(URL, fetch, summarize, tmp_path, tmp_path, sources, TODAY)
    with pytest.raises(DigestError):
        digest_reusing_source(
            OTHER_URL, fetch, summarize, tmp_path, tmp_path, sources, TODAY
        )

    assert seen == [SOURCE, OTHER_SOURCE]


def test_an_unreadable_saved_source_is_fetched_again(tmp_path: Path) -> None:
    seen: list[Source] = []
    fetch = _fetcher()
    summarize = _summarizer(seen, "fail", "fail")
    sources = tmp_path / "sources"

    with pytest.raises(DigestError):
        digest_reusing_source(URL, fetch, summarize, tmp_path, tmp_path, sources, TODAY)
    _corrupt_saved_sources(sources)
    with pytest.raises(DigestError):
        digest_reusing_source(URL, fetch, summarize, tmp_path, tmp_path, sources, TODAY)

    assert seen == [SOURCE, OTHER_SOURCE]


def test_the_bot_reuses_the_source_after_a_restart(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: list[Source] = []
    fetch = _fetcher()
    monkeypatch.setattr("link_digest.botmain.choose_fetch", lambda url: fetch)
    monkeypatch.setattr(
        "link_digest.botmain.summarize", _summarizer(seen, "fail", REPORT)
    )
    sources = tmp_path / "sources"

    with pytest.raises(DigestError):
        _runner(tmp_path, tmp_path, sources)(URL)
    _runner(tmp_path, tmp_path, sources)(URL)

    assert seen == [SOURCE, SOURCE]
