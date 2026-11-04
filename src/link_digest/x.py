"""Read X articles and text posts through the public FxTwitter API."""

import http.client
import json
import re
import urllib.error
import urllib.request
from typing import Any
from urllib.parse import urlsplit

from link_digest.citations import Segment
from link_digest.pipeline import Source
from link_digest.video import fetch_video

_API = "https://api.fxtwitter.com/i/status/"
_TIMEOUT_SECONDS = 30
_SITES = ("x.com", "twitter.com")
_HOSTS = {f"{prefix}{site}" for prefix in ("", "www.", "mobile.") for site in _SITES}
_STATUS_PATH = re.compile(r"/(?:\w+|i/web)/status/([0-9]+)(?:/.*)?")


def status_id(url: str) -> str | None:
    """Return the post id of an X status URL, or None for any other URL."""
    try:
        parts = urlsplit(url)
    except ValueError:
        return None
    if parts.scheme not in ("http", "https") or parts.hostname not in _HOSTS:
        return None
    match = _STATUS_PATH.fullmatch(parts.path)
    return match[1] if match else None


def _paragraphs(texts: list[str]) -> list[Segment]:
    return [
        Segment(number, text.strip())
        for number, text in enumerate((t for t in texts if t.strip()), start=1)
    ]


def source_from_status(url: str, payload: dict[str, Any]) -> Source | None:
    """Turn a FxTwitter response into a text Source, or None for a video post."""
    tweet = payload.get("tweet")
    if payload.get("code") != 200 or not tweet:
        raise ValueError(
            f"FxTwitter returned code {payload.get('code')}: {payload.get('message')}"
        )
    article = tweet.get("article")
    if article:
        blocks = article["content"]["blocks"]
        texts = [b["text"] for b in blocks if b["type"] != "atomic"]
        return Source(url, "article", article.get("title") or "", _paragraphs(texts))
    if (tweet.get("media") or {}).get("videos"):
        return None
    text = tweet.get("text") or ""
    if not text.strip():
        raise ValueError(
            f"FxTwitter returned code {payload['code']} "
            f"with no text: {payload.get('message')}"
        )
    return Source(url, "article", "", _paragraphs(re.split(r"\n\s*\n", text)))


def fetch_x(url: str) -> Source:
    post_id = status_id(url)
    if post_id is None:
        raise ValueError(f"not an X post URL: {url}")
    request = urllib.request.Request(  # noqa: S310 - constant https base, digits-only id
        _API + post_id, headers={"User-Agent": "link-digest"}
    )
    try:
        with urllib.request.urlopen(request, timeout=_TIMEOUT_SECONDS) as response:  # noqa: S310 - same constant https URL
            payload = json.load(response)
    except (
        urllib.error.URLError,
        TimeoutError,
        json.JSONDecodeError,
        http.client.HTTPException,
    ) as err:
        raise RuntimeError(f"could not read X post {post_id}: {err}") from err
    return source_from_status(url, payload) or fetch_video(url)
