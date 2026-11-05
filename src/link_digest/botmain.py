"""Command line entry point of the Telegram bot."""

import argparse
import logging
import os
import sys
import threading
import time
from collections.abc import Callable
from datetime import date
from pathlib import Path
from typing import Any, Protocol

from link_digest.bot import Sender, handle_update, process_next
from link_digest.cli import _DEFAULT_HTML, _DEFAULT_NOTES, choose_fetch
from link_digest.pipeline import Digest, digest_reusing_source
from link_digest.queue import JobQueue
from link_digest.summarize import summarize
from link_digest.telegram import Telegram, TelegramError

log = logging.getLogger(__name__)

_QUEUE_PATH = Path("~/.local/share/link-digest/queue.db")
_SOURCES_PATH = Path("~/.local/share/link-digest/sources")
_POLL_TIMEOUT = 50
_POLL_RETRY_SECONDS = 10
_IDLE_SECONDS = 5
_SEEN = "👀"


class Api(Protocol):
    def get_updates(self, offset: int, timeout: int) -> list[dict[str, Any]]: ...

    def react(self, chat_id: int, message_id: int, emoji: str) -> None: ...


def poll_once(api: Api, allowed_chat_id: int, queue: JobQueue) -> None:
    """Fetch one batch of updates, queue their links and remember how far we got."""
    for update in api.get_updates(queue.get_offset(), _POLL_TIMEOUT):
        added = handle_update(update, allowed_chat_id, queue)
        for message_id in dict.fromkeys(message_id for _, message_id in added):
            try:
                api.react(allowed_chat_id, message_id, _SEEN)
            except TelegramError as err:
                log.warning("could not react to message %d: %s", message_id, err)
        queue.set_offset(update["update_id"] + 1)


def run_until_worker_dies(worker: threading.Thread, poll: Callable[[], None]) -> int:
    """Poll while the worker lives. Exit 1 so systemd restarts a dead worker."""
    while worker.is_alive():
        try:
            poll()
        except TelegramError as err:
            log.warning("polling failed: %s", err)
            time.sleep(_POLL_RETRY_SECONDS)
    return 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="link-digest-bot")
    parser.add_argument(
        "--print-chats",
        action="store_true",
        help="print the id and title of the chats the bot has seen, then exit",
    )
    parser.add_argument("--notes-dir", type=Path, default=_DEFAULT_NOTES)
    parser.add_argument("--html-dir", type=Path, default=_DEFAULT_HTML)
    args = parser.parse_args(argv)

    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        print("TELEGRAM_BOT_TOKEN is not set", file=sys.stderr)
        return 2
    telegram = Telegram(token)
    if args.print_chats:
        return _print_chats(telegram)

    try:
        chat_id = int(os.environ.get("LINK_DIGEST_CHAT_ID", ""))
    except ValueError:
        print(
            "LINK_DIGEST_CHAT_ID must be set to an integer; "
            "find it with: link-digest-bot --print-chats",
            file=sys.stderr,
        )
        return 2

    logging.basicConfig(level=logging.INFO)
    queue = JobQueue(_QUEUE_PATH.expanduser())
    queue.reset_running()
    run = _runner(
        args.notes_dir.expanduser(),
        args.html_dir.expanduser(),
        _SOURCES_PATH.expanduser(),
    )
    worker = threading.Thread(target=_work, args=(queue, run, telegram), daemon=True)
    worker.start()
    return run_until_worker_dies(worker, lambda: poll_once(telegram, chat_id, queue))


def _runner(
    notes_dir: Path, html_dir: Path, sources_dir: Path
) -> Callable[[str], Digest]:
    def run(url: str) -> Digest:
        return digest_reusing_source(
            url,
            choose_fetch(url),
            summarize,
            notes_dir,
            html_dir,
            sources_dir,
            date.today(),
        )

    return run


def _work(
    queue: JobQueue,
    run: Callable[[str], Digest],
    send: Sender,
    forget: Callable[[str], None] = lambda _url: None,
) -> None:
    while True:
        if not process_next(queue, run, send, time.sleep):
            time.sleep(_IDLE_SECONDS)


def _print_chats(telegram: Api) -> int:
    try:
        updates = telegram.get_updates(0, 0)
    except TelegramError as err:
        print(err, file=sys.stderr)
        return 1
    chats: dict[int, str] = {}
    for update in updates:
        chat = update.get("message", {}).get("chat")
        if chat:
            title = chat.get("title") or chat.get("username") or chat.get("first_name")
            chats.setdefault(chat["id"], title or "")
    for chat_id, title in chats.items():
        print(f"{chat_id} {title}")
    return 0
