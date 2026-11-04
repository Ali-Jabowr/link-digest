import pytest

from link_digest.citations import CitationCheck, Segment, check_citations
from link_digest.report import UNVERIFIED_MARK, mark_unverified


@pytest.mark.parametrize(
    ("report", "segments", "expected"),
    [
        pytest.param(
            '[¶3] "dumbest agents"',
            [Segment(3, "the dumbest agents")],
            [CitationCheck("¶3", "dumbest agents", True)],
            id="same_paragraph",
        ),
        pytest.param(
            '[¶3] "dumbest agents"',
            [Segment(4, "the dumbest agents")],
            [CitationCheck("¶3", "dumbest agents", False)],
            id="neighbouring_paragraph_has_no_tolerance",
        ),
        pytest.param(
            '[¶3] "smartest agents"',
            [Segment(3, "the dumbest agents")],
            [CitationCheck("¶3", "smartest agents", False)],
            id="words_not_in_source",
        ),
        pytest.param(
            '[¶3] "end of one start of two"',
            [Segment(3, "end of one"), Segment(4, "start of two")],
            [CitationCheck("¶3", "end of one start of two", True)],
            id="quote_spanning_into_next_paragraph",
        ),
        pytest.param(
            "- point [¶3]",
            [Segment(3, "x")],
            [CitationCheck("¶3", "", False)],
            id="bare_paragraph",
        ),
        pytest.param(
            '[00:10] "alpha" [¶2] "beta"',
            [Segment(10, "alpha"), Segment(2, "beta")],
            [CitationCheck("00:10", "alpha", True), CitationCheck("¶2", "beta", True)],
            id="timestamp_behaviour_unchanged",
        ),
    ],
)
def test_check_citations_handles_paragraph_citations(
    report: str, segments: list[Segment], expected: list[CitationCheck]
) -> None:
    assert check_citations(report, segments) == expected


def test_mark_unverified_marks_an_unverified_paragraph_citation() -> None:
    report = '- point [¶3] "gone" and [¶4] "kept"'
    checks = [CitationCheck("¶3", "gone", False), CitationCheck("¶4", "kept", True)]

    assert (
        mark_unverified(report, checks)
        == f'- point [¶3] "gone"{UNVERIFIED_MARK} and [¶4] "kept"'
    )
