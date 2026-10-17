"""Bedingungen für Sichtbarkeit (config-schema.md §4): Modell und Auswertung.

Die Semantik ist verbindlich identisch zu `frontend/src/shared/lib/conditions.ts` und wird von
beiden Seiten gegen `platform/packages/contracts/condition-vectors.json` geprüft. Kein `eval`.

Festlegungen, die der Vertrag offen lässt (in den Vektoren abgedeckt):
- Ordnungsoperatoren (`gt`, `gte`, `lt`, `lte`) gelten nur für Zahlen; Strings/Booleans ⇒ `false`.
- `neq` ist ebenfalls ein typgleicher Vergleich: Typkonflikt oder unbeantwortet ⇒ `false`.
- Booleans sind keine Zahlen (`True != 1`); Zahlen vergleichen numerisch (`4 == 4.0`).
- „Beantwortet“ = Wert vorhanden und nicht `None`, nicht `""`, keine leere Liste.
"""

from collections.abc import Iterator, Mapping
from typing import Annotated, Final, Literal, Self

from pydantic import (
    ConfigDict,
    Field,
    StrictBool,
    StrictFloat,
    StrictInt,
    StrictStr,
    model_validator,
)

from app.core.pydantic_base import ID_PATTERN, StrictModel

Scalar = StrictBool | StrictInt | StrictFloat | StrictStr
AnswerValue = bool | int | float | str | list[str]
Answers = Mapping[str, AnswerValue]

COMPARISON_OPS: Final = ("eq", "neq", "gt", "gte", "lt", "lte", "in", "not_in", "contains")
ORDER_OPS: Final = ("gt", "gte", "lt", "lte")
Op = Literal[
    "eq", "neq", "gt", "gte", "lt", "lte", "in", "not_in", "contains", "answered", "not_answered"
]


class Leaf(StrictModel):
    item: Annotated[str, Field(pattern=ID_PATTERN)]
    op: Op
    value: Scalar | list[Scalar] | None = None

    @model_validator(mode="after")
    def _value_matches_op(self) -> Self:
        if self.op in ("answered", "not_answered"):
            if self.value is not None:
                raise ValueError(f"op {self.op} takes no value")
        elif self.op in ("in", "not_in"):
            if not isinstance(self.value, list):
                raise ValueError(f"op {self.op} requires a list value")
        elif self.value is None or isinstance(self.value, list):
            raise ValueError(f"op {self.op} requires a scalar value")
        elif self.op in ORDER_OPS and (
            isinstance(self.value, bool) or not isinstance(self.value, int | float)
        ):
            raise ValueError(f"op {self.op} requires a numeric value")
        return self


class All(StrictModel):
    all: list["Condition"]


class Any_(StrictModel):
    any: list["Condition"]


class Not(StrictModel):
    not_: "Condition" = Field(alias="not")

    model_config = ConfigDict(extra="forbid", populate_by_name=True)


Condition = All | Any_ | Not | Leaf

All.model_rebuild()
Any_.model_rebuild()
Not.model_rebuild()


def referenced_items(condition: Condition) -> Iterator[Leaf]:
    """Alle Blätter der Bedingung (Tiefensuche, Reihenfolge wie im Dokument)."""
    if isinstance(condition, Leaf):
        yield condition
    elif isinstance(condition, All):
        for child in condition.all:
            yield from referenced_items(child)
    elif isinstance(condition, Any_):
        for child in condition.any:
            yield from referenced_items(child)
    else:
        yield from referenced_items(condition.not_)


def _is_number(value: object) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool)


def _number(value: object) -> int | float | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return value


def strict_equal(a: object, b: object) -> bool:
    """Typgleiche Gleichheit: Zahl/Zahl, String/String, Bool/Bool; sonst `False`."""
    if _is_number(a) and _is_number(b):
        return bool(a == b)
    if isinstance(a, bool) and isinstance(b, bool):
        return a == b
    if isinstance(a, str) and isinstance(b, str):
        return a == b
    return False


def _same_type(a: object, b: object) -> bool:
    return (
        (_is_number(a) and _is_number(b))
        or (isinstance(a, bool) and isinstance(b, bool))
        or (isinstance(a, str) and isinstance(b, str))
    )


def is_answered(value: object) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return value != ""
    if isinstance(value, list):
        return len(value) > 0
    return True


def _leaf(leaf: Leaf, answers: Answers) -> bool:
    value = answers.get(leaf.item)
    answered = is_answered(value)
    if leaf.op == "answered":
        return answered
    if leaf.op == "not_answered":
        return not answered
    if not answered:
        return False
    target = leaf.value
    if leaf.op == "contains":
        return isinstance(value, list) and any(strict_equal(entry, target) for entry in value)
    if leaf.op in ("in", "not_in"):
        if not isinstance(target, list) or isinstance(value, list):
            return False
        if not any(_same_type(value, entry) for entry in target):
            return False  # Typkonflikt zu allen Listenelementen ⇒ beide Operatoren `false`
        member = any(strict_equal(value, entry) for entry in target)
        return member if leaf.op == "in" else not member
    if isinstance(value, list) or isinstance(target, list) or not _same_type(value, target):
        return False
    if leaf.op == "eq":
        return strict_equal(value, target)
    if leaf.op == "neq":
        return not strict_equal(value, target)
    left, right = _number(value), _number(target)
    if left is None or right is None:
        return False
    if leaf.op == "gt":
        return left > right
    if leaf.op == "gte":
        return left >= right
    if leaf.op == "lt":
        return left < right
    return left <= right


def evaluate(condition: Condition, answers: Answers) -> bool:
    """Wertet die Bedingung über den Antworten sichtbarer Items aus."""
    if isinstance(condition, Leaf):
        return _leaf(condition, answers)
    if isinstance(condition, All):
        return all(evaluate(child, answers) for child in condition.all)
    if isinstance(condition, Any_):
        return any(evaluate(child, answers) for child in condition.any)
    return not evaluate(condition.not_, answers)
