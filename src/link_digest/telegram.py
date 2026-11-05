"""Telegram Bot API client.

The bot token is part of every request URL, so error messages are built only from
the method name, the HTTP status and Telegram's own description. They are logged,
and must never carry the URL or the exception text of a failed request.
"""

import http.client
import json
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Any, Literal

_CALL_TIMEOUT = 30
_UPLOAD_TIMEOUT = 120
_POLL_MARGIN = 10  # seconds on top of the long-poll timeout

ErrorKind = Literal["network", "rate_limited", "rejected"]


class TelegramError(Exception):
    """A Telegram call failed. The message never contains the bot token."""

    def __init__(
        self,
        message: str,
        kind: ErrorKind = "rejected",
        retry_after: int | None = None,
    ) -> None:
        super().__init__(message)
        self.kind = kind
        self.retry_after = retry_after  # seconds Telegram asked us to wait


class Telegram:
    def __init__(self, token: str, base_url: str = "https://api.telegram.org") -> None:
        self._token = token
        self._base_url = base_url

    def get_updates(self, offset: int, timeout: int) -> list[dict[str, Any]]:
        result = self._call(
            "getUpdates",
            {"offset": offset, "timeout": timeout, "allowed_updates": ["message"]},
            timeout + _POLL_MARGIN,
        )
        if not isinstance(result, list):
            raise TelegramError("getUpdates failed: invalid response")
        return result

    def reply(self, chat_id: int, message_id: int, text: str) -> None:
        self._call(
            "sendMessage",
            {
                "chat_id": chat_id,
                "text": text,
                "reply_parameters": {"message_id": message_id},
            },
        )

    def send_status(self, chat_id: int, message_id: int, text: str) -> int:
        return 0

    def edit_status(self, chat_id: int, status_id: int, text: str) -> None:
        pass

    def reply_file(self, chat_id: int, message_id: int, path: Path) -> None:
        boundary = uuid.uuid4().hex
        fields = {
            "chat_id": str(chat_id),
            "reply_parameters": json.dumps({"message_id": message_id}),
        }
        parts = [_field(boundary, name, value) for name, value in fields.items()]
        parts.append(_file(boundary, "document", path))
        parts.append(f"--{boundary}--\r\n".encode())
        self._post(
            "sendDocument",
            b"".join(parts),
            f"multipart/form-data; boundary={boundary}",
            _UPLOAD_TIMEOUT,
        )

    def react(self, chat_id: int, message_id: int, emoji: str) -> None:
        self._call(
            "setMessageReaction",
            {
                "chat_id": chat_id,
                "message_id": message_id,
                "reaction": [{"type": "emoji", "emoji": emoji}],
            },
        )

    def _call(
        self, method: str, fields: dict[str, Any], timeout: int = _CALL_TIMEOUT
    ) -> Any:
        body = json.dumps(fields).encode()
        return self._post(method, body, "application/json", timeout)

    def _post(self, method: str, body: bytes, content_type: str, timeout: int) -> Any:
        request = urllib.request.Request(  # noqa: S310 - base_url is http(s) we set
            f"{self._base_url}/bot{self._token}/{method}",
            data=body,
            headers={"Content-Type": content_type},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 - base_url is http(s) we set
                raw = response.read()
        except urllib.error.HTTPError as err:
            body = err.read()
            raise TelegramError(
                f"{method} failed: HTTP {err.code}{_description(body)}",
                _kind_of_status(err.code),
                _retry_after(body),
            ) from None
        except TimeoutError:
            raise TelegramError(f"{method} failed: timed out", "network") from None
        except (urllib.error.URLError, ConnectionError, http.client.HTTPException):
            raise TelegramError(f"{method} failed: network error", "network") from None
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            # A garbled body comes from something in the way, so it may pass.
            raise TelegramError(
                f"{method} failed: invalid response", "network"
            ) from None
        if not isinstance(data, dict):
            raise TelegramError(f"{method} failed: invalid response", "network")
        if not data.get("ok"):
            description = data.get("description", "unknown error")
            raise TelegramError(f"{method} failed: {description}")
        return data.get("result")


def _kind_of_status(status: int) -> ErrorKind:
    if status == 429:
        return "rate_limited"
    return "network" if status >= 500 else "rejected"


def _error_body(raw: bytes) -> dict[str, Any]:
    """Return a Telegram error body as a dict, or {} if it isn't one."""
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _description(raw: bytes) -> str:
    """Return ": <description>" from a Telegram error body, or "" if it has none."""
    description = _error_body(raw).get("description")
    return f": {description}" if isinstance(description, str) else ""


def _retry_after(raw: bytes) -> int | None:
    """Return the wait Telegram asked for in an error body, if any."""
    parameters = _error_body(raw).get("parameters")
    wait = parameters.get("retry_after") if isinstance(parameters, dict) else None
    return wait if isinstance(wait, int) else None


def _field(boundary: str, name: str, value: str) -> bytes:
    return (
        f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n'
        f"{value}\r\n"
    ).encode()


def _file(boundary: str, name: str, path: Path) -> bytes:
    filename = path.name.translate({ord('"'): "_", ord("\r"): "_", ord("\n"): "_"})
    head = (
        f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"; '
        f'filename="{filename}"\r\nContent-Type: application/octet-stream\r\n\r\n'
    )
    return head.encode() + path.read_bytes() + b"\r\n"
