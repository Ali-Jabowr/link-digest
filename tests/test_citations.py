import pytest

from link_digest.citations import Segment, check_citations


@pytest.mark.parametrize(
    ("report", "segments", "expected"),
    [
        pytest.param(
            '[12:34] "even the dumbest agents"',
            [Segment(754, "even the dumbest agents can do a good job")],
            True,
            id="exact_match_at_timestamp",
        ),
        pytest.param(
            '[12:34] "Even the dumbest agents"',
            [Segment(754, "even, the dumbest agents, can do it")],
            True,
            id="case_and_punctuation_ignored",
        ),
        pytest.param(
            '[12:34] "even the dumbest agents"',
            [
                Segment(754, "so that even the"),
                Segment(758, "dumbest agents can do it"),
            ],
            True,
            id="snippet_split_across_adjacent_segments",
        ),
        pytest.param(
            '[12:34] "dumbest agents"',
            [Segment(695, "dumbest agents")],
            True,
            id="inside_tolerance_59s_early",
        ),
        pytest.param(
            '[12:34] "dumbest agents"',
            [Segment(814, "dumbest agents")],
            True,
            id="at_tolerance_60s_late",
        ),
        pytest.param(
            '[12:34] "dumbest agents"',
            [Segment(815, "dumbest agents")],
            False,
            id="outside_tolerance_61s_late",
        ),
        pytest.param(
            '[12:34] "dumbest agents"',
            [Segment(693, "dumbest agents")],
            False,
            id="outside_tolerance_61s_early",
        ),
        pytest.param(
            '[12:34] "smartest agents"',
            [Segment(754, "dumbest agents")],
            False,
            id="snippet_not_in_transcript",
        ),
    ],
)
def test_citation_is_verified_only_when_snippet_is_near_its_timestamp(
    report: str, segments: list[Segment], expected: bool
) -> None:
    assert [c.verified for c in check_citations(report, segments)] == [expected]
