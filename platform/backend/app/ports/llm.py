"""Port `LlmPort`: Text erzeugen aus einem Prompt und strukturiertem Kontext.

Der Port kennt keine Fachdaten: der Aufrufer reicht nur Text/Fakten herein. Ausgaben sind Entwürfe
und dürfen nie eine Bewertung, Stufe oder Entscheidung bestimmen (docs/RULES.md).
"""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol


class LlmUnavailable(RuntimeError):
    """Der Dienst ist nicht erreichbar oder abgelaufen; der Aufrufer zeigt einen Fallback."""


@dataclass(frozen=True)
class LlmResult:
    text: str
    generator: str
    #: Namen der Kontextfelder, aus denen der Text entstand (Nachvollziehbarkeit)
    source_fields: tuple[str, ...]


class LlmPort(Protocol):
    def complete(self, prompt: str, context: Mapping[str, str]) -> LlmResult: ...
