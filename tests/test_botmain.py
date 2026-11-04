import logging
from pathlib import Path
from typing import Any

import pytest

from link_digest.botmain import main, poll_once
from link_digest.queue import JobQueue
from link_digest.telegram import TelegramError

BOT_ID = "123:abc-not-for-output"
URL = "https://a.example/1"


def _message(update_id: int, chat_id: int, text: str) -> dict[str, Any]:
    return {
        "update_id": update_id,
        "message": {
            "message_id": update_id * 10,
            "chat": {"id": chat_id, "title": f"chat {chat_id}"},
            "text": text,
        },
    }


class FakeApi:
    def __init__(self, updates: list[dict[str, Any]]) -> None:
        self.updates = updates
        self.polls: list[tuple[int, int]] = []
        self.reactions: list[tuple[int, int, str]] = []

    def get_updates(self, offset: int, timeout: int) -> list[dict[str, Any]]:
        self.polls.append((offset, timeout))
        return self.updates

    def react(self, chat_id: int, message_id: int, emoji: str) -> None:
        self.reactions.append((chat_id, message_id, emoji))


class ReactFailsApi(FakeApi):
    def react(self, chat_id: int, message_id: int, emoji: str) -> None:
        raise TelegramError("setMessageReaction failed: HTTP 400")


@pytest.fixture
def queue(tmp_path: Path) -> JobQueue:
    return JobQueue(tmp_path / "queue.db")


def test_main_without_a_token_names_the_variable_and_returns_2(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)

    code = main([])

    assert code == 2
    assert "TELEGRAM_BOT_TOKEN" in capsys.readouterr().err


def test_main_without_a_chat_id_returns_2(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", BOT_ID)
    monkeypatch.delenv("LINK_DIGEST_CHAT_ID", raising=False)

    code = main([])

    captured = capsys.readouterr()
    assert code == 2
    assert "LINK_DIGEST_CHAT_ID" in captured.err
    assert BOT_ID not in captured.err


@pytest.mark.parametrize("value", ["", "abc", "1.5"])
def test_main_with_an_invalid_chat_id_returns_2(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], value: str
) -> None:
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", BOT_ID)
    monkeypatch.setenv("LINK_DIGEST_CHAT_ID", value)

    code = main([])

    captured = capsys.readouterr()
    assert code == 2
    assert "LINK_DIGEST_CHAT_ID" in captured.err
    assert BOT_ID not in captured.err


def test_print_chats_lists_each_distinct_chat_once(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    updates = [
        _message(1, -100, "hi"),
        _message(2, -200, "hello"),
        _message(3, -100, "again"),
        {"update_id": 4, "edited_message": {}},
    ]
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", BOT_ID)
    monkeypatch.delenv("LINK_DIGEST_CHAT_ID", raising=False)
    monkeypatch.setattr("link_digest.botmain.Telegram", lambda token: FakeApi(updates))

    code = main(["--print-chats"])

    captured = capsys.readouterr()
    assert code == 0
    assert captured.out == "-100 chat -100\n-200 chat -200\n"
    assert BOT_ID not in captured.out + captured.err


def test_print_chats_reports_a_telegram_error_and_returns_1(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    class Broken(FakeApi):
        def get_updates(self, offset: int, timeout: int) -> list[dict[str, Any]]:
            raise TelegramError("getUpdates failed: HTTP 401")

    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", BOT_ID)
    monkeypatch.setattr("link_digest.botmain.Telegram", lambda token: Broken([]))

    code = main(["--print-chats"])

    assert code == 1
    assert "getUpdates failed: HTTP 401" in capsys.readouterr().err


def test_poll_once_queues_a_link_reacts_and_saves_the_offset(queue: JobQueue) -> None:
    api = FakeApi([_message(5, -100, f"watch {URL}")])
    queue.set_offset(3)

    poll_once(api, -100, queue)

    assert api.polls == [(3, 50)]
    assert api.reactions == [(-100, 50, "👀")]
    job = queue.next_job()
    assert job is not None
    assert (job.url, job.chat_id, job.message_id) == (URL, -100, 50)
    assert queue.get_offset() == 6


def test_poll_once_ignores_another_chat_but_still_saves_the_offset(
    queue: JobQueue,
) -> None:
    api = FakeApi([_message(8, -999, URL)])

    poll_once(api, -100, queue)

    assert api.reactions == []
    assert queue.next_job() is None
    assert queue.get_offset() == 9


def test_poll_once_does_not_react_to_a_repeated_link(queue: JobQueue) -> None:
    api = FakeApi([_message(5, -100, URL), _message(6, -100, URL)])

    poll_once(api, -100, queue)

    assert api.reactions == [(-100, 50, "👀")]
    assert queue.get_offset() == 7


def test_poll_once_keeps_the_job_when_the_reaction_fails(
    queue: JobQueue, caplog: pytest.LogCaptureFixture
) -> None:
    api = ReactFailsApi([_message(5, -100, URL)])

    with caplog.at_level(logging.WARNING):
        poll_once(api, -100, queue)

    assert "could not react to message 50: setMessageReaction failed: HTTP 400" in (
        caplog.text
    )
    assert queue.next_job() is not None
    assert queue.get_offset() == 6
