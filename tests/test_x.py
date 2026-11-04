from typing import Any

import pytest

from link_digest.citations import Segment
from link_digest.pipeline import Source
from link_digest.x import source_from_status, status_id

_URL = "https://x.com/a/status/1"


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        pytest.param("https://x.com/a/status/123", "123", id="x"),
        pytest.param("https://twitter.com/a_b/status/123", "123", id="twitter"),
        pytest.param("https://www.x.com/a/status/123", "123", id="www"),
        pytest.param("https://mobile.twitter.com/a/status/123", "123", id="mobile"),
        pytest.param("https://x.com/i/status/123", "123", id="i_status"),
        pytest.param("https://x.com/i/web/status/123", "123", id="i_web_status"),
        pytest.param("https://x.com/a/status/123?s=20&t=abc", "123", id="query"),
        pytest.param("https://x.com/a/status/123/photo/1", "123", id="trailing_path"),
        pytest.param("https://evil.com/a/status/1", None, id="other_host"),
        pytest.param("https://x.com.evil.com/a/status/1", None, id="host_prefix"),
        pytest.param("https://evilx.com/a/status/1", None, id="host_suffix"),
        pytest.param("https://x.com/a/status/abc", None, id="non_numeric_id"),
        pytest.param("https://x.com/a", None, id="not_a_status"),
        pytest.param("https://youtu.be/abc", None, id="video_site"),
        pytest.param("not a url", None, id="garbage"),
    ],
)
def test_status_id(url: str, expected: str | None) -> None:
    assert status_id(url) == expected


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        pytest.param(
            {
                "code": 200,
                "tweet": {
                    "text": "",
                    "article": {
                        "title": "T",
                        "content": {
                            "blocks": [
                                {"type": "unstyled", "text": "one"},
                                {"type": "atomic", "text": " "},
                                {"type": "header-two", "text": "two"},
                            ]
                        },
                    },
                },
            },
            Source(_URL, "article", "T", [Segment(1, "one"), Segment(2, "two")]),
            id="article_skips_atomic_blocks_without_using_numbers",
        ),
        pytest.param(
            {
                "code": 200,
                "tweet": {
                    "text": "",
                    "article": {
                        "title": "T",
                        "content": {
                            "blocks": [
                                {"type": "unstyled", "text": "  "},
                                {"type": "unstyled", "text": "only"},
                            ]
                        },
                    },
                },
            },
            Source(_URL, "article", "T", [Segment(1, "only")]),
            id="article_skips_blank_blocks_without_using_numbers",
        ),
        pytest.param(
            {
                "code": 200,
                "tweet": {"text": "hello", "media": {"videos": [{}], "all": [{}]}},
            },
            None,
            id="video_post_falls_back",
        ),
        pytest.param(
            {
                "code": 200,
                "tweet": {"text": "hello\n\nworld", "media": None, "article": None},
            },
            Source(_URL, "article", "", [Segment(1, "hello"), Segment(2, "world")]),
            id="text_post_paragraphs",
        ),
        pytest.param(
            {"code": 200, "tweet": {"text": "a\n\n\n\nb\n"}},
            Source(_URL, "article", "", [Segment(1, "a"), Segment(2, "b")]),
            id="text_post_extra_blank_lines",
        ),
    ],
)
def test_source_from_status(payload: dict[str, Any], expected: Source | None) -> None:
    assert source_from_status(_URL, payload) == expected


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        pytest.param(
            {"code": 404, "message": "NOT_FOUND", "tweet": None},
            "404.*NOT_FOUND",
            id="not_found",
        ),
        pytest.param(
            {"code": 200, "message": "OK"},
            "200.*OK",
            id="missing_tweet",
        ),
        pytest.param(
            {"code": 200, "message": "OK", "tweet": {"text": "  "}},
            "200.*OK",
            id="empty_text_post",
        ),
    ],
)
def test_source_from_status_raises_for_unusable_payloads(
    payload: dict[str, Any], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        source_from_status(_URL, payload)
