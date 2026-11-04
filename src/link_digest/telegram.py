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
from typing import Any

_CALL_TIMEOUT = 30
_UPLOAD_TIMEOUT = 120
_POLL_MARGIN = 10  # seconds on top of the long-poll timeout


class TelegramError(Exception):
    """A Telegram call failed. The message never contains the bot token."""


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
            detail = _description(err.read())
            raise TelegramError(f"{method} failed: HTTP {err.code}{detail}") from None
        except TimeoutError:
            raise TelegramError(f"{method} failed: timed out") from None
        except (urllib.error.URLError, ConnectionError, http.client.HTTPException):
            raise TelegramError(f"{method} failed: network error") from None
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            raise TelegramError(f"{method} failed: invalid response") from None
        if not isinstance(data, dict):
            raise TelegramError(f"{method} failed: invalid response")
        if not data.get("ok"):
            description = data.get("description", "unknown error")
            raise TelegramError(f"{method} failed: {description}")
        return data.get("result")


def _description(raw: bytes) -> str:
    """Return ": <description>" from a Telegram error body, or "" if it has none."""
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return ""
    if isinstance(data, dict) and isinstance(data.get("description"), str):
        return f": {data['description']}"
    return ""


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
