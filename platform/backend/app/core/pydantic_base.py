"""Gemeinsame Pydantic-Basis für Konfigurationsmodelle: unbekannte Felder sind Ladefehler."""

from typing import Final

from pydantic import BaseModel, ConfigDict

ID_PATTERN: Final = r"^[a-z][a-z0-9_]*$"


class StrictModel(BaseModel):
    """Alle Konfigurationsmodelle verbieten unbekannte Felder (Tippfehler = Ladefehler)."""

    model_config = ConfigDict(extra="forbid")
