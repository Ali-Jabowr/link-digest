from datetime import date
from pathlib import Path

import pytest

from link_digest.citations import Segment
from link_digest.pipeline import Source, digest, format_source_lines
from link_digest.summarize import build_prompt

_REPORT = """\
# Title

## In short
Short [¶1] "known words"

## Main points
- a

## Steps and methods
- b

## Tools and references
- c

## Treat with caution
- d

## How you could apply this
- e
"""


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        pytest.param(
            Source("u", "video", "", [Segment(5, "hi"), Segment(65, "there")]),
            "[00:05] hi\n[01:05] there",
            id="video",
        ),
        pytest.param(
            Source("u", "article", "", [Segment(1, "one"), Segment(3, "three")]),
            "[¶1] one\n[¶3] three",
            id="article",
        ),
    ],
)
def test_format_source_lines(source: Source, expected: str) -> None:
    assert format_source_lines(source) == expected


def test_build_prompt_for_an_article_uses_paragraph_form_and_article_label() -> None:
    source = Source("u", "article", "My title", [Segment(1, "one")])

    prompt = build_prompt(source)

    assert '[¶3] "exact words from the source"' in prompt
    assert "Article:\n[¶1] one" in prompt
    assert "Transcript:" not in prompt
    assert '[12:34] "exact words from the source"' not in prompt


def test_build_prompt_for_a_video_is_unchanged() -> None:
    source = Source("u", "video", "post", [Segment(5, "hi")])

    prompt = build_prompt(source)

    assert '[12:34] "exact words from the source"' in prompt
    assert "Post text: post\n\nTranscript:\n[00:05] hi" in prompt


def test_digest_of_an_article_writes_paragraph_lines_and_verifies_citations(
    tmp_path: Path,
) -> None:
    source = Source("u", "article", "T", [Segment(1, "some known words here")])

    result = digest(
        "u",
        lambda _url: source,
        lambda _source: _REPORT,
        tmp_path / "notes",
        tmp_path / "html",
        date(2026, 1, 2),
    )

    transcript = tmp_path / "html" / "2026-01-02 Title.transcript.txt"
    assert transcript.read_text(encoding="utf-8") == "[¶1] some known words here\n"
    assert (result.citations, result.unverified) == (1, 0)
