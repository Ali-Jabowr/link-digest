"""Fetch a source, summarize it, check the citations and write the report files."""

import hashlib
import json
import logging
import re
import subprocess
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path

from link_digest.citations import Segment, check_citations
from link_digest.report import mark_unverified, missing_sections, render_html

log = logging.getLogger(__name__)

_EXPECTED_ERRORS = (OSError, subprocess.CalledProcessError, RuntimeError, ValueError)
_MAX_TITLE = 80


@dataclass(frozen=True)
class Source:
    url: str
    kind: str  # "video" (timestamped segments) or "article" (numbered paragraphs)
    post_text: str  # the text of the post around the content, may be ""
    segments: list[Segment]


@dataclass(frozen=True)
class Digest:
    title: str
    summary: str  # first 600 chars of the "In short" section body
    markdown_path: Path
    html_path: Path
    citations: int
    unverified: int


class DigestError(Exception):
    def __init__(self, step: str, detail: str) -> None:
        super().__init__(f"{step}: {detail}")
        self.step = step
        self.detail = detail


def digest(
    url: str,
    fetch: Callable[[str], Source],
    summarize: Callable[[Source], str],
    notes_dir: Path,
    html_dir: Path,
    today: date,
) -> Digest:
    try:
        source = fetch(url)
    except _EXPECTED_ERRORS as err:
        raise DigestError("fetch", str(err)) from err
    report = _summarize(summarize, source)
    problem = _problem(report, source)
    if problem:
        report = _summarize(summarize, source)
        problem = _problem(report, source)
    if problem:
        raise DigestError("report", problem)
    title = _title(report)
    checks = check_citations(report, source.segments)
    unverified = sum(not check.verified for check in checks)
    marked = mark_unverified(report, checks)
    name = f"{today.isoformat()} {title}"
    md_path = notes_dir / f"{name}.md"
    html_path = html_dir / f"{name}.html"
    notes_dir.mkdir(parents=True, exist_ok=True)
    html_dir.mkdir(parents=True, exist_ok=True)
    md_path.write_text(
        f"---\nsource: {url}\ndate: {today.isoformat()}\n---\n{marked}",
        encoding="utf-8",
    )
    html_path.write_text(render_html(marked, title, url), encoding="utf-8")
    lines = format_source_lines(source)
    (html_dir / f"{name}.transcript.txt").write_text(
        f"{lines}\n" if lines else "", encoding="utf-8"
    )
    return Digest(title, _summary(report), md_path, html_path, len(checks), unverified)


def digest_reusing_source(
    url: str,
    fetch: Callable[[str], Source],
    summarize: Callable[[Source], str],
    notes_dir: Path,
    html_dir: Path,
    sources_dir: Path,
    today: date,
) -> Digest:
    """Make a Digest, keeping the fetched Source on disk until it is finished."""
    saved = sources_dir / f"{hashlib.sha256(url.encode()).hexdigest()}.json"
    result = digest(
        url,
        lambda target: _saved_or_fetched(saved, fetch, target),
        summarize,
        notes_dir,
        html_dir,
        today,
    )
    saved.unlink(missing_ok=True)
    return result


def _saved_or_fetched(saved: Path, fetch: Callable[[str], Source], url: str) -> Source:
    source = _load_source(saved)
    if source is not None:
        return source
    source = fetch(url)
    saved.parent.mkdir(parents=True, exist_ok=True)
    # Written aside first, so a crash can't leave half a Source to be reused.
    partial = saved.with_suffix(".partial")
    partial.write_text(json.dumps(asdict(source)), encoding="utf-8")
    partial.replace(saved)
    return source


def _load_source(saved: Path) -> Source | None:
    try:
        fields = json.loads(saved.read_text(encoding="utf-8"))
        return Source(
            fields["url"],
            fields["kind"],
            fields["post_text"],
            [Segment(s["start_seconds"], s["text"]) for s in fields["segments"]],
        )
    except FileNotFoundError:
        return None
    except (ValueError, KeyError, TypeError) as err:
        log.warning("could not read saved source %s: %s", saved, err)
        return None


def format_timestamp(seconds: int) -> str:
    """Format seconds as mm:ss, or h:mm:ss from one hour up."""
    hours, rest = divmod(seconds, 3600)
    minutes, secs = divmod(rest, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def _format_line(kind: str, segment: Segment) -> str:
    if kind == "article":
        return f"[¶{segment.start_seconds}] {segment.text}"
    return f"[{format_timestamp(segment.start_seconds)}] {segment.text}"


def format_source_lines(source: Source) -> str:
    """One line per segment: [mm:ss] for a video, [¶n] for an article."""
    return "\n".join(_format_line(source.kind, s) for s in source.segments)


def _summarize(summarize: Callable[[Source], str], source: Source) -> str:
    try:
        return summarize(source)
    except _EXPECTED_ERRORS as err:
        raise DigestError("summarize", str(err)) from err


def _problem(report: str, source: Source) -> str:
    """Return why the report is unusable, or "" if it is fine."""
    missing = missing_sections(report)
    if missing:
        return "missing sections: " + ", ".join(missing)
    if not check_citations(report, source.segments):
        return "no citations"
    return ""


def _summary(report: str) -> str:
    body: list[str] = []
    in_section = False
    for line in report.splitlines():
        if line.startswith("## "):
            if in_section:
                break
            in_section = line[3:].strip().casefold() == "in short"
        elif in_section:
            body.append(line)
    return "\n".join(body).strip()[:600]


def _title(report: str) -> str:
    """Return the first `# ` heading made safe for use in a file name."""
    for line in report.splitlines():
        if line.startswith("# "):
            raw = line[2:]
            break
    else:
        return "Untitled"
    cleaned = re.sub(r"[/\\:]", " ", raw)
    cleaned = re.sub(r"\.{2,}", "", cleaned)
    cleaned = re.sub(r"[\"*?<>|#^\[\]]", "", cleaned)  # unsafe in Obsidian or Android
    cleaned = " ".join(cleaned.split())[:_MAX_TITLE].strip(" .")
    return cleaned or "Untitled"
