import subprocess
from collections.abc import Callable
from datetime import date
from pathlib import Path
from typing import NoReturn

import pytest

from link_digest.citations import Segment
from link_digest.pipeline import DigestError, Source, digest

SECTIONS = (
    '## In short\nA talk about bees. [0:05] "bees make honey"\n'
    '## Main points\n- Bees. [1:05] "in the hive"\n'
    "## Steps and methods\nNone.\n"
    "## Tools and references\nNone.\n"
    "## Treat with caution\nNone.\n"
    "## How you could apply this\nNone.\n"
)
REPORT = "# Bee Talk\n" + SECTIONS
SEGMENTS = [
    Segment(5, "bees make honey"),
    Segment(65, "in the hive"),
    Segment(3725, "an hour later"),
]
SOURCE = Source("https://example.com/v", "video", "", SEGMENTS)
TODAY = date(2026, 11, 4)
URL = "https://example.com/v"


def fetch(url: str) -> Source:
    return SOURCE


def raiser(error: Exception) -> Callable[..., NoReturn]:
    def fail(*args: object) -> NoReturn:
        raise error

    return fail


def sequence(*reports: str) -> Callable[[Source], str]:
    remaining = iter(reports)
    return lambda source: next(remaining)


def test_success_writes_markdown_html_and_transcript(tmp_path: Path) -> None:
    notes = tmp_path / "notes"
    html = tmp_path / "html"

    result = digest(URL, fetch, lambda s: REPORT, notes, html, TODAY)

    md = notes / "2026-11-04 Bee Talk.md"
    assert result.markdown_path == md
    assert result.html_path == html / "2026-11-04 Bee Talk.html"
    assert result.title == "Bee Talk"
    assert md.read_text().startswith(
        "---\nsource: https://example.com/v\ndate: 2026-11-04\n---\n"
    )
    assert "<h1>Bee Talk</h1>" in result.html_path.read_text()
    assert (html / "2026-11-04 Bee Talk.transcript.txt").read_text() == (
        "[00:05] bees make honey\n[01:05] in the hive\n[1:02:05] an hour later\n"
    )


def test_summary_is_first_600_chars_of_in_short_body(tmp_path: Path) -> None:
    long_report = REPORT.replace("A talk about bees.", "a" * 700)

    result = digest(URL, fetch, lambda s: long_report, tmp_path, tmp_path, TODAY)

    assert result.summary == "a" * 600


def test_unverified_citations_are_marked_and_counted(tmp_path: Path) -> None:
    report = REPORT.replace('"in the hive"', '"never said this"')

    result = digest(URL, fetch, lambda s: report, tmp_path, tmp_path, TODAY)

    assert result.citations == 2
    assert result.unverified == 1
    assert (
        '- Bees. [1:05] "never said this" **(unverified)**'
        in result.markdown_path.read_text()
    )
    assert "(unverified)" in result.html_path.read_text()


@pytest.mark.parametrize(
    "error",
    [
        pytest.param(OSError("disk"), id="oserror"),
        pytest.param(subprocess.CalledProcessError(1, "yt-dlp"), id="called_process"),
        pytest.param(RuntimeError("boom"), id="runtime"),
        pytest.param(ValueError("bad"), id="value"),
    ],
)
def test_fetch_failure_is_a_fetch_error_and_writes_nothing(
    tmp_path: Path, error: Exception
) -> None:
    with pytest.raises(DigestError) as raised:
        digest(
            URL,
            raiser(error),
            lambda s: REPORT,
            tmp_path / "n",
            tmp_path / "h",
            TODAY,
        )

    assert raised.value.step == "fetch"
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize(
    "error",
    [
        pytest.param(OSError("disk"), id="oserror"),
        pytest.param(subprocess.CalledProcessError(1, "claude"), id="called_process"),
        pytest.param(RuntimeError("boom"), id="runtime"),
        pytest.param(ValueError("bad"), id="value"),
    ],
)
def test_summarize_failure_is_a_summarize_error_and_writes_nothing(
    tmp_path: Path, error: Exception
) -> None:
    with pytest.raises(DigestError) as raised:
        digest(
            URL,
            fetch,
            raiser(error),
            tmp_path / "n",
            tmp_path / "h",
            TODAY,
        )

    assert raised.value.step == "summarize"
    assert list(tmp_path.iterdir()) == []


def test_fetch_error_message_has_step_and_detail(tmp_path: Path) -> None:
    with pytest.raises(DigestError, match=r"^fetch: boom$"):
        digest(
            URL,
            raiser(RuntimeError("boom")),
            lambda s: REPORT,
            tmp_path,
            tmp_path,
            TODAY,
        )


DRAFT = REPORT.replace("# Bee Talk", "# Bad Draft")
NO_CITATIONS = DRAFT.replace('[0:05] "bees make honey"', "").replace(
    '[1:05] "in the hive"', ""
)
MISSING_SECTION = DRAFT.replace("## Treat with caution\nNone.\n", "")


@pytest.mark.parametrize(
    "bad", [MISSING_SECTION, NO_CITATIONS], ids=["section", "cites"]
)
def test_bad_report_is_retried_once_and_good_second_succeeds(
    tmp_path: Path, bad: str
) -> None:
    result = digest(
        URL, fetch, sequence(bad, REPORT), tmp_path / "n", tmp_path / "h", TODAY
    )

    assert result.title == "Bee Talk"
    assert result.markdown_path.exists()


def test_report_missing_section_twice_names_it_and_writes_nothing(
    tmp_path: Path,
) -> None:
    with pytest.raises(DigestError) as raised:
        digest(
            URL,
            fetch,
            sequence(MISSING_SECTION, MISSING_SECTION),
            tmp_path / "n",
            tmp_path / "h",
            TODAY,
        )

    assert str(raised.value) == "report: missing sections: Treat with caution"
    assert list(tmp_path.iterdir()) == []


def test_report_without_citations_twice_is_a_report_error(tmp_path: Path) -> None:
    with pytest.raises(DigestError) as raised:
        digest(
            URL,
            fetch,
            sequence(NO_CITATIONS, NO_CITATIONS),
            tmp_path / "n",
            tmp_path / "h",
            TODAY,
        )

    assert str(raised.value) == "report: no citations"
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize(
    ("heading", "expected_name"),
    [
        pytest.param(
            "# ../../etc/x: a/b", "2026-11-04 etc x a b", id="traversal_and_colon"
        ),
        pytest.param("# " + "t" * 100, "2026-11-04 " + "t" * 80, id="capped_at_80"),
        pytest.param("", "2026-11-04 Untitled", id="no_heading"),
        pytest.param("# ..", "2026-11-04 Untitled", id="only_dots"),
    ],
)
def test_title_becomes_a_safe_filename(
    tmp_path: Path, heading: str, expected_name: str
) -> None:
    report = REPORT.replace("# Bee Talk", heading)
    notes = tmp_path / "notes"

    result = digest(URL, fetch, lambda s: report, notes, tmp_path / "h", TODAY)

    assert result.markdown_path == notes / f"{expected_name}.md"
    assert result.markdown_path.exists()
