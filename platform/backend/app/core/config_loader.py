"""Konfigurationssystem: YAML-Datei laden und gegen ein Pydantic-Schema prüfen.

Fehler nennen Datei und Feldpfad, nie Werte (kein Leck von Inhalten in Logs).
"""

from pathlib import Path
from typing import Any, TypeVar

import yaml
from pydantic import BaseModel, ValidationError

M = TypeVar("M", bound=BaseModel)


class ConfigError(ValueError):
    """Konfigurationsdatei fehlt, ist kein gültiges YAML oder verletzt das Schema."""


def load_yaml_model[M: BaseModel](path: Path, model: type[M]) -> M:
    try:
        raw: Any = yaml.safe_load(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ConfigError(f"{path.name}: cannot be read") from exc
    except yaml.YAMLError as exc:
        raise ConfigError(f"{path.name}: invalid YAML") from exc
    try:
        return model.model_validate(raw)
    except ValidationError as exc:
        fields = ", ".join(".".join(str(p) for p in e["loc"]) or "<root>" for e in exc.errors())
        raise ConfigError(f"{path.name}: schema violation at {fields}") from exc
