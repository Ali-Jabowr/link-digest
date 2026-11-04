"""Check that quoted report snippets appear in the transcript near their cited time."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Segment:
    start_seconds: int
    text: str


@dataclass(frozen=True)
class CitationCheck:
    timestamp: str  # as written in the report, e.g. "12:34"
    snippet: str  # the quoted text as written in the report
    verified: bool


def check_citations(report: str, segments: list[Segment]) -> list[CitationCheck]:
    return []
