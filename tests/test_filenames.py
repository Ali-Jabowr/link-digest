from datetime import date
from pathlib import Path

import pytest

from link_digest.citations import Segment
from link_digest.pipeline import Source, digest

SECTIONS = (
    '## In short\nx\n## Main points\n- a [00:00] "known words"\n'
    "## Steps and methods\n## Tools and references\n"
    "## Treat with caution\n## How you could apply this\n"
)


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        pytest.param('Ask "not" this', "2026-11-04 Ask not this.md", id="quotes"),
        pytest.param("A*B?C<D>E|F", "2026-11-04 ABCDEF.md", id="windows_android"),
        pytest.param("A#B^C[D]E", "2026-11-04 ABCDE.md", id="obsidian_links"),
    ],
)
def test_note_filename_is_safe_for_obsidian_and_android(
    tmp_path: Path, title: str, expected: str
) -> None:
    source = Source("u", "video", "", [Segment(0, "known words")])
    result = digest(
        "u",
        lambda _url: source,
        lambda _source: f"# {title}\n{SECTIONS}",
        tmp_path,
        tmp_path,
        date(2026, 11, 4),
    )
    assert result.markdown_path.name == expected
