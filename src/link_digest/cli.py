"""Command line entry point."""

import argparse
import sys
from collections.abc import Callable
from datetime import date
from pathlib import Path

from link_digest.pipeline import DigestError, Source, digest
from link_digest.summarize import summarize
from link_digest.video import fetch_file, fetch_video
from link_digest.x import fetch_x, status_id

_DEFAULT_NOTES = Path("~/Documents/Obsidian Vaults/Second Brain/Link Digests")
_DEFAULT_HTML = Path("~/.local/share/link-digest/reports")


def choose_fetch(target: str) -> Callable[[str], Source]:
    path = Path(target)
    if path.is_file():
        return lambda _target: fetch_file(path)
    if status_id(target):
        return fetch_x
    return fetch_video


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="link-digest")
    parser.add_argument(
        "target", help="a video or X post URL, or an existing local file"
    )
    parser.add_argument("--notes-dir", type=Path, default=_DEFAULT_NOTES)
    parser.add_argument("--html-dir", type=Path, default=_DEFAULT_HTML)
    args = parser.parse_args(argv)

    try:
        result = digest(
            args.target,
            choose_fetch(args.target),
            summarize,
            args.notes_dir.expanduser(),
            args.html_dir.expanduser(),
            date.today(),
        )
    except DigestError as err:
        print(err, file=sys.stderr)
        return 1

    print(f"report: {result.markdown_path}")
    print(f"html: {result.html_path}")
    print(f"citations: {result.citations}, unverified: {result.unverified}")
    return 0
