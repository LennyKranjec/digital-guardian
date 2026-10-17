"""Port `Notifier`: eine Benachrichtigung zu einem Subjekt auslösen (ohne Zustellversprechen)."""

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


@dataclass(frozen=True)
class Notice:
    subject_id: str | None
    kind: str
    text: str


class Notifier(Protocol):
    def notify(self, notice: Notice, now: datetime) -> None: ...
