from pathlib import Path

import pytest

from link_digest.queue import Job, JobQueue


def _take(queue: JobQueue) -> Job:
    job = queue.next_job()
    assert job is not None
    return job


@pytest.fixture
def queue(tmp_path: Path) -> JobQueue:
    return JobQueue(tmp_path / "queue.db")


def test_next_job_returns_the_oldest_first(queue: JobQueue) -> None:
    queue.add("https://a.example/1", 10, 100)
    queue.add("https://a.example/2", 10, 101)

    first = queue.next_job()
    second = queue.next_job()
    third = queue.next_job()

    assert first == Job(1, "https://a.example/1", 10, 100, 0)
    assert second == Job(2, "https://a.example/2", 10, 101, 0)
    assert third is None


def test_add_refuses_a_url_that_was_queued_before(queue: JobQueue) -> None:
    first = queue.add("https://a.example/1", 10, 100)
    again = queue.add("https://a.example/1", 10, 105)

    assert first is True
    assert again is False


def test_add_refuses_a_url_that_already_completed(queue: JobQueue) -> None:
    queue.add("https://a.example/1", 10, 100)
    job = queue.next_job()
    assert job is not None
    queue.complete(job.id)

    assert queue.add("https://a.example/1", 10, 105) is False
    assert queue.next_job() is None


def test_jobs_survive_reopening_the_file(tmp_path: Path) -> None:
    path = tmp_path / "queue.db"
    JobQueue(path).add("https://a.example/1", 10, 100)

    job = JobQueue(path).next_job()

    assert job == Job(1, "https://a.example/1", 10, 100, 0)


def test_fail_retries_twice_then_gives_up(queue: JobQueue) -> None:
    queue.add("https://a.example/1", 10, 100)

    first = queue.fail(_take(queue).id)
    second = queue.fail(_take(queue).id)
    third = queue.fail(_take(queue).id)

    assert (first, second, third) == (True, True, False)


def test_retried_job_carries_its_attempt_count(queue: JobQueue) -> None:
    queue.add("https://a.example/1", 10, 100)
    job = queue.next_job()
    assert job is not None
    queue.fail(job.id)

    assert queue.next_job() == Job(1, "https://a.example/1", 10, 100, 1)


def test_failed_job_is_not_returned(queue: JobQueue) -> None:
    queue.add("https://a.example/1", 10, 100)
    queue.fail(_take(queue).id)
    queue.fail(_take(queue).id)
    queue.fail(_take(queue).id)

    assert queue.next_job() is None


def test_completed_job_is_not_returned(queue: JobQueue) -> None:
    queue.add("https://a.example/1", 10, 100)
    job = queue.next_job()
    assert job is not None
    queue.complete(job.id)

    assert queue.next_job() is None


def test_running_job_is_not_handed_out_twice(queue: JobQueue) -> None:
    queue.add("https://a.example/1", 10, 100)
    queue.next_job()

    assert queue.next_job() is None


def test_reset_running_puts_jobs_back_to_pending(queue: JobQueue) -> None:
    queue.add("https://a.example/1", 10, 100)
    queue.next_job()

    queue.reset_running()

    assert queue.next_job() == Job(1, "https://a.example/1", 10, 100, 0)


def test_offset_defaults_to_zero(queue: JobQueue) -> None:
    assert queue.get_offset() == 0


def test_offset_persists_across_reopening(tmp_path: Path) -> None:
    path = tmp_path / "queue.db"
    JobQueue(path).set_offset(42)
    JobQueue(path).set_offset(43)

    assert JobQueue(path).get_offset() == 43
