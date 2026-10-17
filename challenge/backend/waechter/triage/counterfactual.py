"""Kontrafaktische (Vertrag §4): exakt durch Aufzählung auf dem Endlevel (Baum + Schild).

- **Würde sinken, wenn …** (`direction = lower`): die kleinsten Änderungen von Symptomgraden, die
  das Endlevel senken. Zuerst Einzel-Symptome (jeweils die nächstliegende Absenkung); gibt es keine,
  Paare (höchstens `max_changed` = 2 Symptome, nur Pareto-minimale). Hält ein Boden das
  Level und senkt keine Änderung es, steht „Boden X verhindert Senkung“ als eigener Eintrag.
- **Nächste Verschlechterung** (`direction = raise`): minimale Erhöhung (+1 je Symptom), die das
  Level anhebt; Einzel-Symptome, sonst Paare.

Die Texte erzeugt die Schicht darüber (i18n, Satzteil ohne Einleitung); hier nur Struktur.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Literal

from waechter.triage.engine import Engine, PreviousGrades
from waechter.triage.kb import Level

MAX_CHANGED = 2
LIMIT = 10


@dataclass(frozen=True)
class Change:
    symptom_key: str
    from_grade: int
    to_grade: int


@dataclass(frozen=True)
class Counterfactual:
    direction: Literal["lower", "raise"]
    kind: Literal["single", "pair", "shield"]
    changes: tuple[Change, ...]
    to_level: Level | None
    floor_id: str | None = None

    @property
    def api_kind(self) -> Literal["change", "shield"]:
        """`kind` im API-Objekt (openapi v2.8): Änderungsvorschlag oder Schild-Hinweis."""
        return "shield" if self.kind == "shield" else "change"

    @property
    def size(self) -> int:
        """Summe der Gradänderungen (Ordnung der Ausgabe)."""
        return sum(abs(c.to_grade - c.from_grade) for c in self.changes)


def _level(
    engine: Engine,
    grades: Mapping[str, int],
    previous: PreviousGrades,
    missing_safety: bool,
) -> Level:
    return engine.level_from_grades(grades, previous, missing_safety=missing_safety).level


def counterfactuals(
    engine: Engine,
    grades: Mapping[str, int],
    previous: PreviousGrades = None,
    *,
    missing_safety: bool = False,
    max_changed: int = MAX_CHANGED,
    limit: int = LIMIT,
) -> list[Counterfactual]:
    """Kontrafaktische zum Endlevel von `grades` (Reihenfolge: senken, dann verschlechtern)."""
    base = engine.level_from_grades(grades, previous, missing_safety=missing_safety)
    lower = _lower(engine, grades, previous, missing_safety, base.level, max_changed, limit)
    if not lower and base.level > Level.GREEN:
        lower = [
            Counterfactual("lower", "shield", (), None, hit.floor_id)
            for hit in base.shield_hits
            if hit.min_level >= base.level
        ]
    raised = _raise(engine, grades, previous, missing_safety, base.level, max_changed, limit)
    return [*lower, *raised]


def _lower(
    engine: Engine,
    grades: Mapping[str, int],
    previous: PreviousGrades,
    missing_safety: bool,
    base: Level,
    max_changed: int,
    limit: int,
) -> list[Counterfactual]:
    if base == Level.GREEN:
        return []
    symptoms = [s for s in engine.profile.symptoms if grades.get(s, 0) > 0]
    singles: list[Counterfactual] = []
    for symptom in symptoms:
        for value in range(grades[symptom] - 1, -1, -1):  # nächstliegende Absenkung zuerst
            level = _level(engine, {**grades, symptom: value}, previous, missing_safety)
            if level < base:
                singles.append(
                    Counterfactual(
                        "lower", "single", (Change(symptom, grades[symptom], value),), level
                    )
                )
                break
    if singles or max_changed < MAX_CHANGED:
        return sorted(singles, key=lambda c: (c.size, c.changes[0].symptom_key))[:limit]
    pairs: list[Counterfactual] = []
    for index, first in enumerate(symptoms):
        for second in symptoms[index + 1 :]:
            found: list[tuple[int, int, Level]] = []
            for v1 in range(grades[first] - 1, -1, -1):
                for v2 in range(grades[second] - 1, -1, -1):
                    level = _level(
                        engine, {**grades, first: v1, second: v2}, previous, missing_safety
                    )
                    if level < base:
                        found.append((v1, v2, level))
                        break
            minimal = [
                (v1, v2, level)
                for v1, v2, level in found
                if not any(o1 >= v1 and o2 >= v2 and (o1, o2) != (v1, v2) for o1, o2, _ in found)
            ]
            pairs.extend(
                Counterfactual(
                    "lower",
                    "pair",
                    (Change(first, grades[first], v1), Change(second, grades[second], v2)),
                    level,
                )
                for v1, v2, level in minimal
            )
    return sorted(
        pairs, key=lambda c: (c.size, c.changes[0].symptom_key, c.changes[1].symptom_key)
    )[:limit]


def _raise(
    engine: Engine,
    grades: Mapping[str, int],
    previous: PreviousGrades,
    missing_safety: bool,
    base: Level,
    max_changed: int,
    limit: int,
) -> list[Counterfactual]:
    if base == Level.RED:
        return []
    caps = {s: engine.profile.items[s].grade_max for s in engine.profile.symptoms}
    symptoms: Sequence[str] = [s for s in engine.profile.symptoms if grades.get(s, 0) < caps[s]]
    singles: list[Counterfactual] = []
    for symptom in symptoms:
        level = _level(engine, {**grades, symptom: grades[symptom] + 1}, previous, missing_safety)
        if level > base:
            singles.append(
                Counterfactual(
                    "raise",
                    "single",
                    (Change(symptom, grades[symptom], grades[symptom] + 1),),
                    level,
                )
            )
    if singles or max_changed < MAX_CHANGED:
        return singles[:limit]
    pairs: list[Counterfactual] = []
    for index, first in enumerate(symptoms):
        for second in symptoms[index + 1 :]:
            raised = {**grades, first: grades[first] + 1, second: grades[second] + 1}
            level = _level(engine, raised, previous, missing_safety)
            if level > base:
                pairs.append(
                    Counterfactual(
                        "raise",
                        "pair",
                        (
                            Change(first, grades[first], grades[first] + 1),
                            Change(second, grades[second], grades[second] + 1),
                        ),
                        level,
                    )
                )
    return pairs[:limit]
