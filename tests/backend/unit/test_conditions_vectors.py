"""Zusätzliche Bedingungsvektoren (platform/packages/contracts/condition-vectors-extra.json).

Erwartungen wurden aus config-schema.md §4 von Hand abgeleitet, nicht aus der Implementierung.
Dieselbe Datei läuft im Browser in tests/e2e/specs/conditions.spec.ts.
"""

import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import TypeAdapter

from app.core.conditions import Condition, evaluate

VECTORS_PATH = (
    Path(__file__).resolve().parents[3]
    / "platform"
    / "packages"
    / "contracts"
    / "condition-vectors-extra.json"
)
VECTORS: list[dict[str, Any]] = json.loads(VECTORS_PATH.read_text(encoding="utf-8"))
ADAPTER: TypeAdapter[Condition] = TypeAdapter(Condition)


def test_a3_vector_file_is_sane() -> None:
    assert len(VECTORS) >= 10
    assert len({v["name"] for v in VECTORS}) == len(VECTORS)


@pytest.mark.parametrize("vector", VECTORS, ids=[v["name"] for v in VECTORS])
def test_a3_condition_vector(vector: dict[str, Any]) -> None:
    condition = ADAPTER.validate_python(vector["condition"])
    assert evaluate(condition, vector["answers"]) is vector["expected"]
