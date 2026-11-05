"""The bot's logic: find links in messages, queue them, and answer finished jobs."""

import logging
import re
import time
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urlsplit, urlunsplit

from link_digest.pipeline import Digest, DigestError
from link_digest.queue import Job, JobQueue
from link_digest.telegram import TelegramError

log = logging.getLogger(__name__)

_URL = re.compile(r"https?://\S+")
_TRAILING = ".,;:!?)]}'\""
_X_HOSTS = {"x.com", "www.x.com", "twitter.com", "www.twitter.com"}
_MAX_MESSAGE = 4000
_BACKOFF_START = 5  # seconds
_BACKOFF_MAX = 300  # seconds


class Sender(Protocol):
    def reply(self, chat_id: int, message_id: int, text: str) -> None: ...

    def reply_file(self, chat_id: int, message_id: int, path: Path) -> None: ...


def extract_links(text: str, hidden: Iterable[str] = ()) -> list[str]:
    """Return every http(s) URL, visible then hidden, without duplicates."""
    links: dict[str, None] = {}  # a dict keeps insertion order
    for match in _URL.finditer(text):
        links[_clean(match.group().rstrip(_TRAILING))] = None
    for url in hidden:
        if _URL.fullmatch(url):
            links[_clean(url)] = None
    return list(links)


def handle_update(
    update: dict[str, Any], allowed_chat_id: int, queue: JobQueue
) -> list[tuple[str, int]]:
    """Queue the new links of an update. Return (url, message_id) for each one."""
    message = update.get("message")
    if not message or message.get("chat", {}).get("id") != allowed_chat_id:
        return []
    text = message.get("text") or message.get("caption") or ""
    message_id = message["message_id"]
    entities = message.get("entities", []) + message.get("caption_entities", [])
    hidden = [e["url"] for e in entities if e["type"] == "text_link"]
    return [
        (url, message_id)
        for url in extract_links(text, hidden)
        if queue.add(url, allowed_chat_id, message_id)
    ]


def format_summary(digest: Digest, url: str) -> str:
    """Build the reply text. Only the summary is cut, so counts and url survive."""
    head = f"{digest.title}\n\n"
    tail = f"\n\nCitations: {digest.citations}, unverified: {digest.unverified}\n{url}"
    room = _MAX_MESSAGE - len(head) - len(tail)
    summary = digest.summary
    if len(summary) > room:
        summary = summary[: room - 1].rstrip() + "…"
    return head + summary + tail


def process_next(
    queue: JobQueue,
    run: Callable[[str], Digest],
    send: Sender,
    sleep: Callable[[float], None] = lambda _seconds: None,
    clock: Callable[[], float] = time.monotonic,
    forget: Callable[[str], None] = lambda _url: None,
) -> bool:
    """Run the oldest job. Return False if there was none."""
    job = queue.next_job()
    if job is None:
        return False
    digest = job.digest
    if digest is None:
        started = clock()
        try:
            digest = run(job.url)
        except DigestError as err:
            if not queue.fail(job.id):
                forget(job.url)
                _notify_failure(send, job.chat_id, job.message_id, job.url, err)
            return True
        except Exception:
            # Count it so a job that always crashes can't restart the bot forever.
            if not queue.fail(job.id):
                forget(job.url)
            raise
        queue.record_run(job.id, digest.kind, clock() - started)
        queue.save_digest(job.id, digest)
    try:
        if not job.summary_sent:
            send.reply(job.chat_id, job.message_id, format_summary(digest, job.url))
            queue.mark_summary_sent(job.id)
        send.reply_file(job.chat_id, job.message_id, digest.html_path)
    except TelegramError as err:
        # A retry sends only what is still missing.
        _after_failed_delivery(queue, job, digest, err, sleep)
        return True
    except Exception:
        queue.fail(job.id)
        raise
    queue.complete(job.id)
    return True


def _after_failed_delivery(
    queue: JobQueue,
    job: Job,
    digest: Digest,
    err: TelegramError,
    sleep: Callable[[float], None],
) -> None:
    if err.kind == "rejected":
        if queue.fail(job.id):
            log.warning("could not deliver %s: %s", job.url, err)
        else:
            log.error(
                "gave up delivering %s: %s; the report stays at %s",
                job.url,
                err,
                digest.html_path,
            )
        return
    log.warning("could not deliver %s: %s", job.url, err)
    queue.retry_delivery(job.id)
    sleep(err.retry_after or min(_BACKOFF_START * 2**job.attempts, _BACKOFF_MAX))


def _notify_failure(
    send: Sender, chat_id: int, message_id: int, url: str, err: DigestError
) -> None:
    try:
        send.reply(chat_id, message_id, f"Could not process {url}: {err}")
    except TelegramError as send_err:
        log.warning("could not report the failure of %s: %s", url, send_err)


def _clean(url: str) -> str:
    """Drop the tracking query from x.com and twitter.com status links."""
    parts = urlsplit(url)
    if parts.hostname in _X_HOSTS and "/status/" in parts.path:
        return urlunsplit(parts._replace(query=""))
    return url
