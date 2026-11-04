"""Command line entry point."""

import argparse
import sys
from datetime import date
from pathlib import Path

from link_digest.pipeline import DigestError, digest
from link_digest.summarize import summarize
from link_digest.video import fetch_file, fetch_video

_DEFAULT_NOTES = Path("~/Documents/Obsidian Vaults/Second Brain/Link Digests")
_DEFAULT_HTML = Path("~/.local/share/link-digest/reports")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="link-digest")
    parser.add_argument("target", help="a video URL or an existing local file")
    parser.add_argument("--notes-dir", type=Path, default=_DEFAULT_NOTES)
    parser.add_argument("--html-dir", type=Path, default=_DEFAULT_HTML)
    args = parser.parse_args(argv)

    path = Path(args.target)
    fetch = (lambda _target: fetch_file(path)) if path.is_file() else fetch_video
    try:
        result = digest(
            args.target,
            fetch,
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
