"""Keep one status message per Job, edited in place as the Job moves on."""

import logging
from typing import Protocol

from link_digest.queue import JobQueue
from link_digest.telegram import TelegramError

log = logging.getLogger(__name__)

FETCHING = "Fetching the Source"
WRITING = "Writing the Report"
SENDING = "Sending"
DONE = "Done"


class StatusApi(Protocol):
    def send_status(self, chat_id: int, message_id: int, text: str) -> int: ...

    def edit_status(self, chat_id: int, status_id: int, text: str) -> None: ...


class JobStatus:
    def __init__(self, api: StatusApi, queue: JobQueue) -> None:
        self._api = api
        self._queue = queue

    def queued(self, url: str) -> None:
        self.show(url, f"Queued ({self._queue.links_ahead(url)} ahead)")

    def show(self, url: str, text: str) -> None:
        """Show a state. A Telegram failure is logged and never reaches the Job."""
        target = self._queue.status_target(url)
        if target is None:
            return
        chat_id, message_id, status_id = target
        try:
            if status_id is None:
                new_id = self._api.send_status(chat_id, message_id, text)
                self._queue.set_status_message(url, new_id)
            else:
                self._api.edit_status(chat_id, status_id, text)
        except TelegramError as err:
            log.warning("could not update the status of %s: %s", url, err)
