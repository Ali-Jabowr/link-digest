import sqlite3
from contextlib import closing
from pathlib import Path

from link_digest.pipeline import Digest
from link_digest.queue import JobQueue

DIGEST = Digest("T", "S", Path("/n/1.md"), Path("/h/1.html"), 1, 0, "video")
SAVED_BEFORE_KINDS = (
    '{"title": "T", "summary": "S", "markdown_path": "/n/1.md", '
    '"html_path": "/h/1.html", "citations": 1, "unverified": 0}'
)


def test_a_saved_digest_keeps_its_kind_when_loaded(tmp_path: Path) -> None:
    queue = JobQueue(tmp_path / "queue.db")
    queue.add("https://a.example/1", 10, 100)
    job = queue.next_job()
    assert job is not None
    queue.save_digest(job.id, DIGEST)
    queue.retry_delivery(job.id)

    loaded = queue.next_job()

    assert loaded is not None
    assert loaded.digest == DIGEST


def test_a_digest_saved_before_kinds_existed_still_loads(tmp_path: Path) -> None:
    path = tmp_path / "queue.db"
    queue = JobQueue(path)
    queue.add("https://a.example/1", 10, 100)
    with closing(sqlite3.connect(path)) as conn, conn:
        conn.execute("UPDATE jobs SET digest = ?", (SAVED_BEFORE_KINDS,))

    loaded = queue.next_job()

    assert loaded is not None
    assert loaded.digest == Digest(
        "T", "S", Path("/n/1.md"), Path("/h/1.html"), 1, 0, ""
    )
