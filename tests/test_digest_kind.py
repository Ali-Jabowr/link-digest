from datetime import date
from pathlib import Path

import pytest

from link_digest.citations import Segment
from link_digest.pipeline import Source, digest

SECTIONS = (
    "## Main points\nNone.\n"
    "## Steps and methods\nNone.\n"
    "## Tools and references\nNone.\n"
    "## Treat with caution\nNone.\n"
    "## How you could apply this\nNone.\n"
)
URL = "https://example.com/v"


@pytest.mark.parametrize(
    ("kind", "citation"),
    [
        ("video", '[0:05] "bees make honey"'),
        ("article", '[¶5] "bees make honey"'),
    ],
)
def test_digest_reports_the_kind_of_its_source(
    tmp_path: Path, kind: str, citation: str
) -> None:
    source = Source(URL, kind, "", [Segment(5, "bees make honey")])
    report = f"# Bee Talk\n## In short\nBees. {citation}\n{SECTIONS}"

    result = digest(
        URL,
        lambda _url: source,
        lambda _source: report,
        tmp_path,
        tmp_path,
        date(2026, 11, 5),
    )

    assert result.kind == kind
