import socket
import threading
from collections.abc import Iterator

import pytest
from test_telegram import FakeTelegramServer

from link_digest.telegram import Telegram, TelegramError


@pytest.fixture
def server() -> Iterator[FakeTelegramServer]:
    fake = FakeTelegramServer()
    thread = threading.Thread(target=fake.serve_forever, daemon=True)
    thread.start()
    yield fake
    fake.shutdown()
    fake.server_close()
    thread.join()


@pytest.mark.parametrize(
    ("status", "reply", "kind", "retry_after"),
    [
        pytest.param(500, b"oops", "network", None, id="server_error"),
        pytest.param(502, b"<html>Bad</html>", "network", None, id="bad_gateway"),
        pytest.param(200, b"not json", "network", None, id="garbled_body"),
        pytest.param(
            429,
            b'{"ok": false, "parameters": {"retry_after": 37}}',
            "rate_limited",
            37,
            id="rate_limited_with_wait",
        ),
        pytest.param(429, b"not json", "rate_limited", None, id="rate_limited_bare"),
        pytest.param(403, b'{"ok": false}', "rejected", None, id="forbidden"),
        pytest.param(400, b'{"ok": false}', "rejected", None, id="bad_request"),
        pytest.param(200, b'{"ok": false}', "rejected", None, id="not_ok"),
    ],
)
def test_error_kinds(
    server: FakeTelegramServer,
    status: int,
    reply: bytes,
    kind: str,
    retry_after: int | None,
) -> None:
    server.status = status
    server.reply = reply

    with pytest.raises(TelegramError) as excinfo:
        Telegram("123:abc", server.base_url).reply(-100, 7, "hello")

    assert (excinfo.value.kind, excinfo.value.retry_after) == (kind, retry_after)


def test_unreachable_server_is_a_network_error() -> None:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]

    with pytest.raises(TelegramError) as excinfo:
        Telegram("123:abc", f"http://127.0.0.1:{port}").reply(-100, 7, "hello")

    assert excinfo.value.kind == "network"
