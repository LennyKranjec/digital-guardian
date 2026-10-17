"""Benachrichtigungskanal (Plattform-Port `Notifier`). Standard: In-App-Mock, im Speicher.

Der Kanal ist austauschbar (`set_notifier`); Zustellung wird nie zugesagt. Die persistente
In-App-Liste steht in `wa_notifications`, der Port ist der Hook für weitere Kanäle.
"""

from app.adapters.memory_notifier import MemoryNotifier
from app.ports.notifier import Notifier

_notifier: Notifier = MemoryNotifier()


def get_notifier() -> Notifier:
    return _notifier


def set_notifier(notifier: Notifier) -> None:
    global _notifier
    _notifier = notifier
