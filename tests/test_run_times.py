from pathlib import Path

import pytest

from link_digest.queue import JobQueue


@pytest.fixture
def queue(tmp_path: Path) -> JobQueue:
    return JobQueue(tmp_path / "queue.db")


def test_run_seconds_returns_only_the_times_of_the_asked_kind(queue: JobQueue) -> None:
    for number in (1, 2, 3):
        queue.add(f"https://a.example/{number}", 10, 100 + number)
        job = queue.next_job()
        assert job is not None
        kind = "article" if number == 2 else "video"
        queue.record_run(job.id, kind, (30.0, 5.0, 50.0)[number - 1])

    assert queue.run_seconds("video") == [30.0, 50.0]
    assert queue.run_seconds("article") == [5.0]
    assert queue.run_seconds("unknown") == []
