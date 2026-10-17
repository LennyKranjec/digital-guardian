"""Bedingungs-Evaluator gegen die gemeinsamen Testvektoren (identisch zu Vitest, H2)."""

import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import TypeAdapter, ValidationError

from app.core.conditions import Condition, evaluate, referenced_items
from app.core.settings import REPO_ROOT

VECTORS_PATH = Path(REPO_ROOT) / "platform" / "packages" / "contracts" / "condition-vectors.json"
VECTORS: list[dict[str, Any]] = json.loads(VECTORS_PATH.read_text(encoding="utf-8"))
ADAPTER: TypeAdapter[Condition] = TypeAdapter(Condition)


def test_vector_file_has_required_size_and_shape() -> None:
    assert len(VECTORS) >= 30
    assert all(set(vector) == {"name", "condition", "answers", "expected"} for vector in VECTORS)
    assert len({vector["name"] for vector in VECTORS}) == len(VECTORS)
    assert {True, False} == {vector["expected"] for vector in VECTORS}


@pytest.mark.parametrize("vector", VECTORS, ids=[vector["name"] for vector in VECTORS])
def test_condition_vector(vector: dict[str, Any]) -> None:
    condition = ADAPTER.validate_python(vector["condition"])
    assert evaluate(condition, vector["answers"]) is vector["expected"]


def test_all_operators_are_covered_by_vectors() -> None:
    used: set[str] = set()
    for vector in VECTORS:
        used.update(
            leaf.op for leaf in referenced_items(ADAPTER.validate_python(vector["condition"]))
        )
    assert used == {
        "eq",
        "neq",
        "gt",
        "gte",
        "lt",
        "lte",
        "in",
        "not_in",
        "contains",
        "answered",
        "not_answered",
    }


@pytest.mark.parametrize(
    "bad",
    [
        {"item": "a", "op": "eq"},
        {"item": "a", "op": "gte", "value": "4"},
        {"item": "a", "op": "in", "value": 4},
        {"item": "a", "op": "answered", "value": 1},
        {"item": "a", "op": "eq", "value": [1]},
        {"item": "a", "op": "regex", "value": "x"},
        {"item": "a", "op": "eq", "value": 1, "extra": True},
        {"all": [], "any": []},
        {"python": "__import__('os')"},
    ],
)
def test_invalid_conditions_are_rejected(bad: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        ADAPTER.validate_python(bad)
