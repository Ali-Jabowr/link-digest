from pathlib import Path
from typing import Any

import pytest
from test_botmain import FakeApi

from link_digest.botmain import poll_once
from link_digest.queue import Job, JobQueue

URL = "https://a.example/1"
HIDDEN = {"type": "text_link", "offset": 0, "length": 4, "url": URL}


@pytest.mark.parametrize(
    ("fields", "expected"),
    [
        pytest.param(
            {"text": "read this", "entities": [HIDDEN]},
            Job(1, URL, -100, 50, 0),
            id="in_text",
        ),
        pytest.param(
            {"caption": "read this", "caption_entities": [HIDDEN]},
            Job(1, URL, -100, 50, 0),
            id="in_caption",
        ),
        pytest.param(
            {
                "text": "read this",
                "entities": [
                    {
                        "type": "text_link",
                        "offset": 0,
                        "length": 4,
                        "url": "https://x.com/a/status/1?s=20",
                    }
                ],
            },
            Job(1, "https://x.com/a/status/1", -100, 50, 0),
            id="cleaned_like_a_visible_link",
        ),
        pytest.param(
            {
                "text": "read this",
                "entities": [
                    {
                        "type": "text_link",
                        "offset": 0,
                        "length": 4,
                        "url": "tg://user?id=1",
                    }
                ],
            },
            None,
            id="not_a_web_link",
        ),
        pytest.param(
            {"text": "@someone", "entities": [{"type": "mention", "offset": 0}]},
            None,
            id="other_entity",
        ),
    ],
)
def test_hidden_link(
    tmp_path: Path, fields: dict[str, Any], expected: Job | None
) -> None:
    queue = JobQueue(tmp_path / "queue.db")
    update = {
        "update_id": 5,
        "message": {"message_id": 50, "chat": {"id": -100}, **fields},
    }

    poll_once(FakeApi([update]), -100, queue)

    assert queue.next_job() == expected


def test_visible_and_hidden_copies_of_a_link_make_one_job(tmp_path: Path) -> None:
    queue = JobQueue(tmp_path / "queue.db")
    update = {
        "update_id": 5,
        "message": {
            "message_id": 50,
            "chat": {"id": -100},
            "text": f"{URL} and again",
            "entities": [HIDDEN],
        },
    }

    poll_once(FakeApi([update]), -100, queue)

    assert queue.next_job() == Job(1, URL, -100, 50, 0)
    assert queue.next_job() is None


def test_two_different_links_make_two_jobs_with_the_visible_one_first(
    tmp_path: Path,
) -> None:
    queue = JobQueue(tmp_path / "queue.db")
    update = {
        "update_id": 5,
        "message": {
            "message_id": 50,
            "chat": {"id": -100},
            "text": "see https://b.example/2",
            "entities": [HIDDEN],
        },
    }

    poll_once(FakeApi([update]), -100, queue)

    assert queue.next_job() == Job(1, "https://b.example/2", -100, 50, 0)
    assert queue.next_job() == Job(2, URL, -100, 50, 0)
