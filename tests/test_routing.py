from pathlib import Path

from link_digest.cli import choose_fetch
from link_digest.video import fetch_video
from link_digest.x import fetch_x


def test_x_status_url_uses_fetch_x() -> None:
    assert choose_fetch("https://x.com/a/status/1") is fetch_x


def test_other_url_uses_fetch_video() -> None:
    assert choose_fetch("https://youtu.be/abc") is fetch_video


def test_existing_file_uses_neither_url_fetcher(tmp_path: Path) -> None:
    clip = tmp_path / "clip.wav"
    clip.write_bytes(b"")

    fetch = choose_fetch(str(clip))

    assert callable(fetch)
    assert fetch is not fetch_x
    assert fetch is not fetch_video
