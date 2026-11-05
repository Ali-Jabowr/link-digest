"""Read X articles, text posts and Threads through the public FxTwitter API."""

import dataclasses
import http.client
import json
import logging
import re
import urllib.error
import urllib.request
from typing import Any
from urllib.parse import urlsplit

from link_digest.citations import Segment
from link_digest.pipeline import Source
from link_digest.video import fetch_video

log = logging.getLogger(__name__)

_API = "https://api.fxtwitter.com/i/status/"
_THREAD_API = "https://api.fxtwitter.com/2/thread/"
_NO_THREAD = "Only this post was read: its Thread could not be looked up."
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
    return Source(url, "article", "", _paragraphs(_split(text)))


def _split(text: str) -> list[str]:
    return re.split(r"\n\s*\n", text)


def _thread_texts(payload: dict[str, Any]) -> list[str]:
    """Return the paragraphs of the linked post's author, in Thread order."""
    author = payload["status"]["author"]["screen_name"]
    texts: list[str] = []
    for post in payload["thread"]:
        if post["author"]["screen_name"] != author:
            continue
        texts += _split(post["text"])
        quote = post.get("quote")
        if quote:
            words = " ".join(quote["text"].split())
            quoted = quote["author"]["screen_name"]
            texts.append(f"Quoted post by @{quoted}: {words}")
    return texts


def _read_json(api_url: str, post_id: str) -> dict[str, Any]:
    request = urllib.request.Request(  # noqa: S310 - constant https base, digits-only id
        api_url, headers={"User-Agent": "link-digest"}
    )
    try:
        with urllib.request.urlopen(request, timeout=_TIMEOUT_SECONDS) as response:  # noqa: S310 - same constant https URL
            payload: dict[str, Any] = json.load(response)
    except (OSError, json.JSONDecodeError, http.client.HTTPException) as err:
        raise RuntimeError(f"could not read X post {post_id}: {err}") from err
    return payload


def _fetch_single_post(url: str, post_id: str) -> Source:
    payload = _read_json(_API + post_id, post_id)
    return source_from_status(url, payload) or fetch_video(url)


def fetch_x(url: str) -> Source:
    post_id = status_id(url)
    if post_id is None:
        raise ValueError(f"not an X post URL: {url}")
    # /2/thread looks undocumented, so any surprise in it falls back to the post.
    try:
        payload = _read_json(_THREAD_API + post_id, post_id)
        status = payload["status"]
        texts = _thread_texts(payload)
        paragraphs = _paragraphs(texts)
        if not paragraphs:
            raise ValueError("the Thread has no text")
    except (RuntimeError, ValueError, KeyError, TypeError) as err:
        log.warning("could not read the Thread of X post %s: %r", post_id, err)
        source = _fetch_single_post(url, post_id)
        return dataclasses.replace(source, note=_NO_THREAD)
    if status.get("article"):
        return _fetch_single_post(url, post_id)
    if (status.get("media") or {}).get("videos"):
        thread_text = "\n\n".join(text.strip() for text in texts)
        return dataclasses.replace(fetch_video(url), post_text=thread_text)
    return Source(url, "article", "", paragraphs)
