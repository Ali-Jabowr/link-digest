import json
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any

import pytest

from link_digest.bot import process_next
from link_digest.botmain import _announce_fetched, _work, poll_once
from link_digest.citations import Segment
from link_digest.pipeline import Digest, DigestError, Source
from link_digest.queue import JobQueue
from link_digest.status import JobStatus
from link_digest.telegram import Telegram, TelegramError

URL = "https://a.example/1"
OTHER_URL = "https://a.example/2"
CHAT = -100
MESSAGE = 7
STATUS_ID = 900
DIGEST = Digest("Title", "Short.", Path("/n/1.md"), Path("/h/1.html"), 3, 0, "video")
SOURCE = Source(URL, "video", "", [Segment(1, "words")])


class Stop(BaseException):
    """Ends the endless worker loop: no handler in the bot catches it."""


class FakeTelegram:
    """Records status calls and replies, like the real client's two sides."""

    def __init__(self) -> None:
        self.statuses: list[tuple[str, int, int, str]] = []
        self.replies: list[str] = []

    def send_status(self, chat_id: int, message_id: int, text: str) -> int:
        self.statuses.append(("send", chat_id, message_id, text))
        return STATUS_ID

    def edit_status(self, chat_id: int, status_id: int, text: str) -> None:
        self.statuses.append(("edit", chat_id, status_id, text))

    def reply(self, chat_id: int, message_id: int, text: str) -> None:
        self.replies.append(text)

    def reply_file(self, chat_id: int, message_id: int, path: Path) -> None:
        pass


class StatusDownTelegram(FakeTelegram):
    def send_status(self, chat_id: int, message_id: int, text: str) -> int:
        raise TelegramError("sendMessage failed: HTTP 400")

    def edit_status(self, chat_id: int, status_id: int, text: str) -> None:
        raise TelegramError("editMessageText failed: HTTP 400")


class OutageTelegram(FakeTelegram):
    def reply(self, chat_id: int, message_id: int, text: str) -> None:
        raise TelegramError("sendMessage failed: network error", "network")


class RejectingTelegram(FakeTelegram):
    def reply(self, chat_id: int, message_id: int, text: str) -> None:
        raise TelegramError("sendMessage failed: HTTP 400")


@pytest.fixture
def queue(tmp_path: Path) -> JobQueue:
    jobs = JobQueue(tmp_path / "queue.db")
    jobs.add(URL, CHAT, MESSAGE)
    return jobs


def _texts(telegram: FakeTelegram) -> list[str]:
    return [call[3] for call in telegram.statuses]


def _finished(url: str) -> Digest:
    return DIGEST


def _fails(url: str) -> Digest:
    raise DigestError("fetch", "boom")


def test_the_first_status_is_a_reply_to_the_owners_message(queue: JobQueue) -> None:
    telegram = FakeTelegram()

    JobStatus(telegram, queue).queued(URL)

    assert telegram.statuses == [("send", CHAT, MESSAGE, "Queued (0 ahead)")]


def test_queued_counts_the_links_ahead(queue: JobQueue) -> None:
    telegram = FakeTelegram()
    queue.add(OTHER_URL, CHAT, 8)

    JobStatus(telegram, queue).queued(OTHER_URL)

    assert _texts(telegram) == ["Queued (1 ahead)"]


def test_a_successful_job_edits_one_message_through_to_done(queue: JobQueue) -> None:
    telegram = FakeTelegram()
    status = JobStatus(telegram, queue)
    status.queued(URL)

    process_next(queue, _finished, telegram, status=status.show)

    assert telegram.statuses == [
        ("send", CHAT, MESSAGE, "Queued (0 ahead)"),
        ("edit", CHAT, STATUS_ID, "Fetching the Source"),
        ("edit", CHAT, STATUS_ID, "Sending"),
        ("edit", CHAT, STATUS_ID, "Done"),
    ]


def test_a_failed_try_shows_the_next_attempt_and_the_reason(queue: JobQueue) -> None:
    telegram = FakeTelegram()
    status = JobStatus(telegram, queue)

    process_next(queue, _fails, telegram, status=status.show)

    assert _texts(telegram) == [
        "Fetching the Source",
        "Retrying (attempt 2/3): fetch: boom",
    ]


def test_giving_up_shows_failed_and_still_sends_its_own_reply(queue: JobQueue) -> None:
    telegram = FakeTelegram()
    status = JobStatus(telegram, queue)

    process_next(queue, _fails, telegram, status=status.show)
    process_next(queue, _fails, telegram, status=status.show)
    process_next(queue, _fails, telegram, status=status.show)

    assert _texts(telegram)[-2:] == [
        "Fetching the Source",
        "Failed: fetch: boom",
    ]
    assert telegram.replies == [f"Could not process {URL}: fetch: boom"]


def test_a_delivery_outage_shows_retrying_with_the_reason(queue: JobQueue) -> None:
    telegram = OutageTelegram()
    status = JobStatus(telegram, queue)

    process_next(queue, _finished, telegram, status=status.show)

    assert _texts(telegram) == [
        "Fetching the Source",
        "Sending",
        "Retrying (attempt 2): sendMessage failed: network error",
    ]


def test_a_rejected_delivery_counts_from_its_own_first_try(queue: JobQueue) -> None:
    telegram = RejectingTelegram()
    status = JobStatus(telegram, queue)

    process_next(queue, _finished, telegram, status=status.show)

    assert (
        _texts(telegram)[-1] == "Retrying (attempt 2/3): sendMessage failed: HTTP 400"
    )


def test_after_a_restart_the_bot_keeps_editing_the_same_message(tmp_path: Path) -> None:
    path = tmp_path / "queue.db"
    JobQueue(path).add(URL, CHAT, MESSAGE)
    JobStatus(FakeTelegram(), JobQueue(path)).queued(URL)
    telegram = FakeTelegram()

    JobStatus(telegram, JobQueue(path)).show(URL, "Sending")

    assert telegram.statuses == [("edit", CHAT, STATUS_ID, "Sending")]


def test_a_status_failure_never_fails_or_retries_the_job(queue: JobQueue) -> None:
    telegram = StatusDownTelegram()
    status = JobStatus(telegram, queue)

    process_next(queue, _finished, telegram, status=status.show)

    assert queue.next_job() is None
    assert queue.add(URL, CHAT, MESSAGE) is False


def test_a_resent_failed_link_starts_a_new_status_message(queue: JobQueue) -> None:
    status = JobStatus(FakeTelegram(), queue)
    status.queued(URL)
    process_next(queue, _fails, FakeTelegram())
    process_next(queue, _fails, FakeTelegram())
    process_next(queue, _fails, FakeTelegram())
    queue.add(URL, CHAT, 8)
    telegram = FakeTelegram()

    JobStatus(telegram, queue).queued(URL)

    assert telegram.statuses == [("send", CHAT, 8, "Queued (0 ahead)")]


def test_writing_is_shown_once_the_source_is_fetched() -> None:
    shown: list[str] = []
    fetch = _announce_fetched(lambda url: SOURCE, lambda: shown.append("fetched"))

    assert fetch(URL) == SOURCE
    assert shown == ["fetched"]


def test_a_failed_fetch_does_not_announce_writing() -> None:
    shown: list[str] = []

    def fails(url: str) -> Source:
        raise RuntimeError("boom")

    fetch = _announce_fetched(fails, lambda: shown.append("fetched"))

    with pytest.raises(RuntimeError):
        fetch(URL)
    assert shown == []


def test_polling_announces_each_new_link(tmp_path: Path) -> None:
    class Api:
        def get_updates(self, offset: int, timeout: int) -> list[dict[str, Any]]:
            return [
                {
                    "update_id": 1,
                    "message": {
                        "message_id": MESSAGE,
                        "chat": {"id": CHAT},
                        "text": f"{URL} {OTHER_URL}",
                    },
                }
            ]

        def react(self, chat_id: int, message_id: int, emoji: str) -> None:
            pass

    announced: list[str] = []

    poll_once(Api(), CHAT, JobQueue(tmp_path / "queue.db"), announced.append)

    assert announced == [URL, OTHER_URL]


def test_the_worker_passes_status_updates_through(
    queue: JobQueue, monkeypatch: pytest.MonkeyPatch
) -> None:
    def stop(_seconds: float) -> None:
        raise Stop

    shown: list[str] = []
    monkeypatch.setattr("link_digest.botmain.time.sleep", stop)

    with pytest.raises(Stop):
        _work(queue, _finished, FakeTelegram(), lambda url, text: shown.append(text))

    assert shown == ["Fetching the Source", "Sending", "Done"]


class _ScriptedServer(HTTPServer):
    def __init__(self, status: int, reply: dict[str, Any]) -> None:
        super().__init__(("127.0.0.1", 0), _Handler)
        self.status = status
        self.reply = json.dumps(reply).encode()
        self.paths: list[str] = []
        self.bodies: list[dict[str, Any]] = []


class _Handler(BaseHTTPRequestHandler):
    server: _ScriptedServer

    def do_POST(self) -> None:
        body = self.rfile.read(int(self.headers["Content-Length"]))
        self.server.paths.append(self.path)
        self.server.bodies.append(json.loads(body))
        self.send_response(self.server.status)
        self.send_header("Content-Length", str(len(self.server.reply)))
        self.end_headers()
        self.wfile.write(self.server.reply)

    def log_message(self, format: str, *args: object) -> None:
        return None


def _serve(status: int, reply: dict[str, Any]) -> Iterator[_ScriptedServer]:
    server = _ScriptedServer(status, reply)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server
    server.shutdown()
    server.server_close()
    thread.join()


@pytest.fixture
def sent_server() -> Iterator[_ScriptedServer]:
    yield from _serve(200, {"ok": True, "result": {"message_id": STATUS_ID}})


@pytest.fixture
def edited_server() -> Iterator[_ScriptedServer]:
    yield from _serve(200, {"ok": True, "result": {"message_id": STATUS_ID}})


@pytest.fixture
def not_modified_server() -> Iterator[_ScriptedServer]:
    yield from _serve(
        400,
        {
            "ok": False,
            "description": "Bad Request: message is not modified: same content",
        },
    )


@pytest.fixture
def rejecting_server() -> Iterator[_ScriptedServer]:
    yield from _serve(
        400, {"ok": False, "description": "Bad Request: message to edit not found"}
    )


def _client(server: _ScriptedServer) -> Telegram:
    return Telegram("1:x", f"http://127.0.0.1:{server.server_port}")


def test_send_status_replies_quietly_and_returns_the_new_message_id(
    sent_server: _ScriptedServer,
) -> None:
    assert _client(sent_server).send_status(CHAT, MESSAGE, "Queued") == STATUS_ID
    assert sent_server.paths == ["/bot1:x/sendMessage"]
    assert sent_server.bodies == [
        {
            "chat_id": CHAT,
            "text": "Queued",
            "disable_notification": True,
            "reply_parameters": {
                "message_id": MESSAGE,
                "allow_sending_without_reply": True,
            },
        }
    ]


def test_edit_status_edits_the_message_in_place(
    edited_server: _ScriptedServer,
) -> None:
    _client(edited_server).edit_status(CHAT, STATUS_ID, "Done")

    assert edited_server.paths == ["/bot1:x/editMessageText"]
    assert edited_server.bodies == [
        {"chat_id": CHAT, "message_id": STATUS_ID, "text": "Done"}
    ]


def test_editing_to_the_same_text_is_not_an_error(
    not_modified_server: _ScriptedServer,
) -> None:
    _client(not_modified_server).edit_status(CHAT, STATUS_ID, "Done")


def test_other_edit_rejections_are_still_errors(
    rejecting_server: _ScriptedServer,
) -> None:
    with pytest.raises(TelegramError, match="message to edit not found"):
        _client(rejecting_server).edit_status(CHAT, STATUS_ID, "Done")
