import json
import socket
import threading
from collections.abc import Iterator
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

from link_digest.telegram import Telegram, TelegramError

BOT_ID = "123:SECRET-BOT_ID"
OK = b'{"ok": true, "result": true}'


@dataclass(frozen=True)
class Request:
    path: str
    content_type: str
    body: bytes


class FakeTelegramServer(HTTPServer):
    """A real local HTTP server that records requests and sends a canned reply."""

    def __init__(self) -> None:
        super().__init__(("127.0.0.1", 0), _Handler)
        self.requests: list[Request] = []
        self.status = 200
        self.reply = OK

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.server_port}"


class _Handler(BaseHTTPRequestHandler):
    server: FakeTelegramServer

    def do_POST(self) -> None:
        length = int(self.headers["Content-Length"])
        body = self.rfile.read(length)
        content_type = self.headers["Content-Type"]
        self.server.requests.append(Request(self.path, content_type, body))
        self.send_response(self.server.status)
        self.send_header("Content-Length", str(len(self.server.reply)))
        self.end_headers()
        self.wfile.write(self.server.reply)

    def log_message(self, format: str, *args: object) -> None:
        return None


@pytest.fixture
def server() -> Iterator[FakeTelegramServer]:
    fake = FakeTelegramServer()
    thread = threading.Thread(target=fake.serve_forever, daemon=True)
    thread.start()
    yield fake
    fake.shutdown()
    fake.server_close()
    thread.join()


def _only(server: FakeTelegramServer) -> Request:
    assert len(server.requests) == 1
    return server.requests[0]


def test_reply_sends_json_with_reply_parameters_and_no_parse_mode(
    server: FakeTelegramServer,
) -> None:
    Telegram(BOT_ID, server.base_url).reply(-100, 7, "hello")

    request = _only(server)
    assert request.path == "/bot123:SECRET-BOT_ID/sendMessage"
    assert request.content_type == "application/json"
    assert json.loads(request.body) == {
        "chat_id": -100,
        "text": "hello",
        "reply_parameters": {"message_id": 7},
    }


def test_get_updates_posts_offset_timeout_and_allowed_updates(
    server: FakeTelegramServer,
) -> None:
    server.reply = b'{"ok": true, "result": [{"update_id": 5}]}'

    updates = Telegram(BOT_ID, server.base_url).get_updates(5, 0)

    assert updates == [{"update_id": 5}]
    request = _only(server)
    assert request.path == "/bot123:SECRET-BOT_ID/getUpdates"
    assert json.loads(request.body) == {
        "offset": 5,
        "timeout": 0,
        "allowed_updates": ["message"],
    }


def test_react_sends_an_emoji_reaction(server: FakeTelegramServer) -> None:
    Telegram(BOT_ID, server.base_url).react(-100, 7, "👀")

    request = _only(server)
    assert request.path == "/bot123:SECRET-BOT_ID/setMessageReaction"
    assert json.loads(request.body) == {
        "chat_id": -100,
        "message_id": 7,
        "reaction": [{"type": "emoji", "emoji": "👀"}],
    }


def test_reply_file_sends_multipart_with_the_file_bytes(
    server: FakeTelegramServer, tmp_path: Path
) -> None:
    report = tmp_path / "2026-11-04 A Title.html"
    report.write_bytes(b"<html>\xc3\xa9 report body</html>")

    Telegram(BOT_ID, server.base_url).reply_file(-100, 7, report)

    request = _only(server)
    assert request.path == "/bot123:SECRET-BOT_ID/sendDocument"
    assert request.content_type.startswith("multipart/form-data; boundary=")
    assert b"<html>\xc3\xa9 report body</html>" in request.body
    assert b'filename="2026-11-04 A Title.html"' in request.body
    assert b'name="chat_id"\r\n\r\n-100\r\n' in request.body
    assert b'name="reply_parameters"\r\n\r\n{"message_id": 7}\r\n' in request.body


@pytest.mark.parametrize(
    ("status", "reply", "message"),
    [
        (
            403,
            b'{"ok": false, "description": "Forbidden: bot was kicked"}',
            "sendMessage failed: HTTP 403: Forbidden: bot was kicked",
        ),
        (502, b"<html>Bad Gateway</html>", "sendMessage failed: HTTP 502"),
        (
            200,
            b'{"ok": false, "description": "Bad Request: chat not found"}',
            "sendMessage failed: Bad Request: chat not found",
        ),
        (200, b"not json", "sendMessage failed: invalid response"),
    ],
)
def test_errors_raise_telegram_error_without_the_token(
    server: FakeTelegramServer, status: int, reply: bytes, message: str
) -> None:
    server.status = status
    server.reply = reply

    with pytest.raises(TelegramError) as excinfo:
        Telegram(BOT_ID, server.base_url).reply(-100, 7, "hello")

    assert str(excinfo.value) == message
    assert BOT_ID not in str(excinfo.value)
    assert "SECRET" not in repr(excinfo.value.__cause__)


def test_unreachable_server_raises_telegram_error_without_the_token() -> None:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]

    with pytest.raises(TelegramError) as excinfo:
        Telegram(BOT_ID, f"http://127.0.0.1:{port}").get_updates(0, 0)

    assert str(excinfo.value) == "getUpdates failed: network error"
