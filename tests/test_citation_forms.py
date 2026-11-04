import pytest

from link_digest.citations import CitationCheck, Segment, check_citations


@pytest.mark.parametrize(
    ("report", "segments", "expected"),
    [
        pytest.param(
            '[12:34] "even the... dumbest agents"',
            [Segment(754, "even the most naive right the dumbest agents")],
            [CitationCheck("12:34", "even the... dumbest agents", True)],
            id="ellipsis_parts_in_order",
        ),
        pytest.param(
            '[12:34] "dumbest agents... even the"',
            [Segment(754, "even the dumbest agents")],
            [CitationCheck("12:34", "dumbest agents... even the", False)],
            id="ellipsis_parts_out_of_order",
        ),
        pytest.param(
            '[12:34] "even the dumbest agents"',
            [
                Segment(754, "even the"),
                Segment(760, "something else"),
                Segment(770, "dumbest agents"),
            ],
            [CitationCheck("12:34", "even the dumbest agents", False)],
            id="gap_between_segments",
        ),
        pytest.param(
            '[1:02:03] "dumbest agents"',
            [Segment(3723, "dumbest agents")],
            [CitationCheck("1:02:03", "dumbest agents", True)],
            id="hours_timestamp",
        ),
        pytest.param(
            '- point [00:10] "alpha" more [00:20] "beta"',
            [Segment(10, "alpha"), Segment(500, "beta")],
            [
                CitationCheck("00:10", "alpha", True),
                CitationCheck("00:20", "beta", False),
            ],
            id="two_citations_in_report_order",
        ),
        pytest.param(
            "- point [12:34]",
            [Segment(754, "x")],
            [CitationCheck("12:34", "", False)],
            id="bare_timestamp",
        ),
        pytest.param(
            "- point [12:34–13:00]",
            [Segment(754, "x")],
            [CitationCheck("12:34", "", False), CitationCheck("13:00", "", False)],
            id="bare_range",
        ),
        pytest.param(
            "- point [12:34, 13:00]",
            [Segment(754, "x")],
            [CitationCheck("12:34", "", False), CitationCheck("13:00", "", False)],
            id="bare_comma_list",
        ),
        pytest.param(
            "[12:34] “dumbest agents”",
            [Segment(754, "dumbest agents")],
            [CitationCheck("12:34", "dumbest agents", True)],
            id="curly_quotes",
        ),
    ],
)
def test_check_citations_handles_citation_forms(
    report: str, segments: list[Segment], expected: list[CitationCheck]
) -> None:
    assert check_citations(report, segments) == expected
