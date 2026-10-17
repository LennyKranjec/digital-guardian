"""`MemoryNotifier`: sammelt Benachrichtigungen im Speicher (Mock des `Notifier`-Ports)."""

from datetime import datetime

from app.ports.notifier import Notice


class MemoryNotifier:
    def __init__(self) -> None:
        self.sent: list[tuple[datetime, Notice]] = []

    def notify(self, notice: Notice, now: datetime) -> None:
        self.sent.append((now, notice))
