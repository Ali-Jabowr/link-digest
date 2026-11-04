from pathlib import Path

import pytest

from link_digest.cli import main
from link_digest.pipeline import Source


def test_fetch_failure_prints_the_error_and_returns_1(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    def boom(url: str) -> Source:
        raise RuntimeError("boom")

    monkeypatch.setattr("link_digest.cli.fetch_video", boom)

    code = main(
        [
            "https://example.com/x",
            "--notes-dir",
            str(tmp_path / "notes"),
            "--html-dir",
            str(tmp_path / "html"),
        ]
    )

    assert code == 1
    assert "fetch: boom" in capsys.readouterr().err
