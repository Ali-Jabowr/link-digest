import io
import json
from collections.abc import Callable
from datetime import date
from pathlib import Path
from typing import Any

import pytest
from test_pipeline import REPORT
from test_pipeline import SOURCE as PIPELINE_SOURCE

from link_digest.citations import Segment
from link_digest.pipeline import Source, digest
from link_digest.x import fetch_x

URL = "https://x.com/author/status/1483922203158536193"
THREAD: dict[str, Any] = json.loads(
    (Path(__file__).parent / "fixtures" / "fxtwitter_thread.json").read_text("utf-8")
)
SINGLE_POST = {
    "code": 200,
    "tweet": {"text": "Only this post.\n\nSecond paragraph.", "media": {}},
}
VIDEO = Source(URL, "video", "the video description", [Segment(3, "spoken words")])


def _serve(*responses: dict[str, Any] | Exception) -> Callable[..., io.BytesIO]:
    """Answer each lookup in turn with a JSON body, or fail with an exception."""
    remaining = iter(responses)

    def urlopen(request: Any, timeout: float) -> io.BytesIO:
        response = next(remaining)
        if isinstance(response, Exception):
            raise response
        return io.BytesIO(json.dumps(response).encode())

    return urlopen


def _with_post(payload: dict[str, Any], post: dict[str, Any]) -> dict[str, Any]:
    return {**payload, "thread": [*payload["thread"], post]}


def test_a_thread_becomes_one_article_with_continuous_paragraph_numbers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("link_digest.x.urllib.request.urlopen", _serve(THREAD))

    source = fetch_x(URL)

    assert source.kind == "article"
    assert source.note == ""
    assert source.segments[0] == Segment(
        1, "I started writing threads on Twitter in 2019."
    )
    assert source.segments[5] == Segment(6, "Template #1: The Framework Thread")
    assert source.segments[-1].start_seconds == 16


def test_a_quoted_post_becomes_a_labelled_paragraph(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("link_digest.x.urllib.request.urlopen", _serve(THREAD))

    assert fetch_x(URL).segments[9] == Segment(
        10,
        "Quoted post by @author: In 2021, I published 4 books. In 2022, I plan on "
        "publishing 8. Here's the 5-step framework I use to write 60,000+ words in "
        "30 hours or less (2,000 words per hour) 👇",
    )


def test_replies_from_other_people_are_left_out(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reply = {"text": "Great thread!", "author": {"screen_name": "someone"}}
    monkeypatch.setattr(
        "link_digest.x.urllib.request.urlopen", _serve(_with_post(THREAD, reply))
    )

    assert fetch_x(URL).segments[-1].start_seconds == 16


def test_a_linked_video_post_stays_a_video_with_the_thread_as_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    video_status = {**THREAD["status"], "media": {"videos": [{"url": "v.mp4"}]}}
    payload = {
        "code": 200,
        "status": video_status,
        "thread": [{"text": "One.\n\nTwo.", "author": {"screen_name": "author"}}],
    }
    monkeypatch.setattr("link_digest.x.urllib.request.urlopen", _serve(payload))
    monkeypatch.setattr("link_digest.x.fetch_video", lambda url: VIDEO)

    assert fetch_x(URL) == Source(URL, "video", "One.\n\nTwo.", VIDEO.segments)


def test_an_x_article_is_still_read_as_an_article(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    article = {
        "title": "A long read",
        "content": {"blocks": [{"type": "unstyled", "text": "Body."}]},
    }
    thread = {**THREAD, "status": {**THREAD["status"], "article": article}}
    single = {"code": 200, "tweet": {"article": article}}
    monkeypatch.setattr("link_digest.x.urllib.request.urlopen", _serve(thread, single))

    assert fetch_x(URL) == Source(URL, "article", "A long read", [Segment(1, "Body.")])


@pytest.mark.parametrize(
    "failed_lookup",
    [
        OSError("connection reset"),
        {"code": 404, "message": "NOT_FOUND"},
        {"code": 200, "unexpected": "shape"},
    ],
)
def test_a_failed_thread_lookup_falls_back_to_the_single_post_and_says_so(
    monkeypatch: pytest.MonkeyPatch, failed_lookup: dict[str, Any] | Exception
) -> None:
    monkeypatch.setattr(
        "link_digest.x.urllib.request.urlopen", _serve(failed_lookup, SINGLE_POST)
    )

    assert fetch_x(URL) == Source(
        URL,
        "article",
        "",
        [Segment(1, "Only this post."), Segment(2, "Second paragraph.")],
        note="Only this post was read: its Thread could not be looked up.",
    )


def test_the_summary_says_so_when_a_source_carries_a_note(tmp_path: Path) -> None:
    source = Source(
        PIPELINE_SOURCE.url,
        PIPELINE_SOURCE.kind,
        PIPELINE_SOURCE.post_text,
        PIPELINE_SOURCE.segments,
        note="Only this post was read.",
    )

    result = digest(
        source.url,
        lambda url: source,
        lambda s: REPORT,
        tmp_path,
        tmp_path,
        date(2026, 11, 5),
    )

    assert result.summary.startswith("Only this post was read.\n\n")
