"""Check that quoted report snippets appear in the transcript near their cited time."""

import re
from dataclasses import dataclass

TOLERANCE_SECONDS = 60

_TIME = r"\d+(?::\d+){1,2}"
_CITATION = re.compile(
    rf"\[(?P<times>{_TIME}(?:\s*[,–-]\s*{_TIME})*)\](?:\s*[\"“](?P<quote>[^\"”]*)[\"”])?"
)


@dataclass(frozen=True)
class Segment:
    start_seconds: int
    text: str


@dataclass(frozen=True)
class CitationCheck:
    timestamp: str  # as written in the report, e.g. "12:34"
    snippet: str  # the quoted text as written in the report
    verified: bool


def _normalize(text: str) -> list[str]:
    return re.sub(r"[^\w\s]", "", text.lower()).split()


def _seconds(timestamp: str) -> int:
    seconds = 0
    for part in timestamp.split(":"):
        seconds = seconds * 60 + int(part)
    return seconds


def _find_near(
    part: list[str], words: list[str], starts: list[int], position: int, cited: int
) -> int | None:
    """Return the end index of the first match at or after position near cited."""
    for i in range(position, len(words) - len(part) + 1):
        window = starts[i : i + len(part)]
        if words[i : i + len(part)] == part and any(
            abs(start - cited) <= TOLERANCE_SECONDS for start in window
        ):
            return i + len(part)
    return None


def _is_verified(snippet: str, cited: int, segments: list[Segment]) -> bool:
    words: list[str] = []
    starts: list[int] = []
    for segment in segments:
        segment_words = _normalize(segment.text)
        words += segment_words
        starts += [segment.start_seconds] * len(segment_words)

    parts = [_normalize(part) for part in re.split(r"\.\.\.|…", snippet)]
    parts = [part for part in parts if part]
    if not parts:
        return False

    position = 0
    for part in parts:
        end = _find_near(part, words, starts, position, cited)
        if end is None:
            return False
        position = end
    return True


def find_citations(report: str) -> list[tuple[int, list[tuple[str, str]]]]:
    """Return (end offset, [(timestamp, snippet), ...]) for each citation in the report.

    A range or list of timestamps, or a timestamp without a quote, has snippet "".
    """
    found = []
    for match in _CITATION.finditer(report):
        timestamps = re.findall(_TIME, match["times"])
        quote = match["quote"] if len(timestamps) == 1 else None
        found.append((match.end(), [(ts, quote or "") for ts in timestamps]))
    return found


def check_citations(report: str, segments: list[Segment]) -> list[CitationCheck]:
    return [
        CitationCheck(ts, snippet, _is_verified(snippet, _seconds(ts), segments))
        for _, cited in find_citations(report)
        for ts, snippet in cited
    ]
