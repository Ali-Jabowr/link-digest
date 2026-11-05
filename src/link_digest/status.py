"""Keep one status message per Job, edited in place as the Job moves on."""

from typing import Protocol

from link_digest.queue import JobQueue


class StatusApi(Protocol):
    def send_status(self, chat_id: int, message_id: int, text: str) -> int: ...

    def edit_status(self, chat_id: int, status_id: int, text: str) -> None: ...


class JobStatus:
    def __init__(self, api: StatusApi, queue: JobQueue) -> None:
        self._api = api
        self._queue = queue

    def queued(self, url: str) -> None:
        pass

    def show(self, url: str, text: str) -> None:
        pass
