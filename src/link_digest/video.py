"""Fetch a video's audio with yt-dlp and transcribe it with faster-whisper."""

import json
import os
import subprocess
import tempfile
from pathlib import Path

from link_digest.citations import Segment
from link_digest.pipeline import Source

_MODEL = "deepdml/faster-whisper-large-v3-turbo-ct2"
_STDERR_TAIL = 1000


def transcribe(audio: Path) -> list[Segment]:
    # The model is already cached; never contact the Hub.
    os.environ["HF_HUB_OFFLINE"] = "1"
    from faster_whisper import WhisperModel

    model = WhisperModel(_MODEL, device="cpu", compute_type="int8")
    segments, _info = model.transcribe(str(audio), beam_size=1, vad_filter=True)
    return [Segment(int(s.start), s.text.strip()) for s in segments]


def fetch_video(url: str) -> Source:
    with tempfile.TemporaryDirectory() as tmp:
        directory = Path(tmp)
        command = [
            "yt-dlp",
            "--no-playlist",
            "-f",
            "bestaudio",
            "-x",
            "--audio-format",
            "wav",
            "--postprocessor-args",
            "ffmpeg:-ar 16000 -ac 1",
            "--write-info-json",
            "-o",
            str(directory / "audio.%(ext)s"),
            "--",
            url,
        ]
        try:
            subprocess.run(  # noqa: S603 - argument list, no shell
                command, check=True, capture_output=True, text=True, timeout=3600
            )
        except subprocess.CalledProcessError as err:
            raise RuntimeError(f"yt-dlp failed: {err.stderr[-_STDERR_TAIL:]}") from err
        except subprocess.TimeoutExpired as err:
            raise RuntimeError(f"yt-dlp timed out after {err.timeout}s") from err
        info = json.loads((directory / "audio.info.json").read_text(encoding="utf-8"))
        post_text = info.get("description") or ""
        return Source(url, "video", post_text, transcribe(directory / "audio.wav"))


def fetch_file(path: Path) -> Source:
    return Source(str(path), "video", "", transcribe(path))
