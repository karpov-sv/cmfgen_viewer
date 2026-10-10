"""Application-local change notifications for job event streams."""

from threading import Condition


class ChangeSignal:
    def __init__(self):
        self._condition = Condition()
        self._version = 0

    @property
    def version(self) -> int:
        with self._condition:
            return self._version

    def notify(self) -> None:
        with self._condition:
            self._version += 1
            self._condition.notify_all()

    def wait(self, version: int, timeout: float) -> int:
        with self._condition:
            self._condition.wait_for(lambda: self._version != version, timeout=timeout)
            return self._version
