"""Triage-Engines: Symptomgrade, Aggregate, Lehrerregeln, Böden (Schild) und Entscheidung.

`TeacherEngine` wertet die Lehrerregeln direkt aus (Referenz, Vergleichsbasis der Verifikation);
`CompiledEngine` wertet die kompilierten Bäume aus (Standard im Betrieb). Beide sind reine
Funktionen: keine Uhr, kein Zufall, kein LLM. Hook H2: beide halten `components` und bilden
`max(Komponentenlevel…)`, danach `max(…, Böden)`; Reason-Codes tragen die `component_id` (bei einer
Komponente = Profil-ID). `final = max(Lehrer bzw. Baum, Böden)`; fehlende Safety-Information ergibt
nie GREEN (mindestens YELLOW, `incomplete`, Reason `INCOMPLETE_SAFETY_ITEMS`).

Monotonie (Vertrag §1): Grade, Aggregate und Regeln sind in den Antworten nicht fallend; Böden sind
beim Laden auf Monotonie geprüft, die Bäume bei der Verifikation. Eine höhere Antwort senkt das
Endlevel deshalb nie.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Final, Literal, Protocol

from waechter.triage import parser
from waechter.triage.compiler import CompiledComponent, compiled_for
from waechter.triage.kb import (
    AggregateDef,
    Level,
    ResolvedComposition,
    ResolvedProfile,
    RuleDef,
    State,
    compose,
)

__all__ = [
    "INCOMPLETE_SAFETY_ITEMS",
    "CompiledEngine",
    "ComponentLevel",
    "Decision",
    "Engine",
    "LeafRef",
    "Level",
    "Reason",
    "ShieldHit",
    "TeacherEngine",
    "aggregate_value",
]

INCOMPLETE_SAFETY_ITEMS: Final = "INCOMPLETE_SAFETY_ITEMS"

type PreviousGrades = Mapping[str, int] | None


@dataclass(frozen=True)
class ShieldHit:
    """Ein ausgelöster Boden: ID, Mindeststufe und die auslösenden Symptome (Grad ≥ 1)."""

    floor_id: str
    min_level: Level
    items: tuple[str, ...]


@dataclass(frozen=True)
class Reason:
    """Ein Grund der Entscheidung mit der Komponente, aus der er stammt (Hook H2)."""

    code: str
    component_id: str
    kind: Literal["shield", "rule", "incomplete"]


@dataclass(frozen=True)
class LeafRef:
    """Blätter, in denen der Merkmalsvektor einer Komponente landete (nur `CompiledEngine`)."""

    component_id: str
    yellow: str
    red: str


@dataclass(frozen=True)
class ComponentLevel:
    component_id: str
    level: Level


@dataclass(frozen=True)
class Decision:
    level: Level
    reason_codes: tuple[str, ...]
    incomplete: bool
    shield_hits: tuple[ShieldHit, ...] = ()
    reasons: tuple[Reason, ...] = field(default=(), compare=False)
    leaves: tuple[LeafRef, ...] = field(default=(), compare=False)
    components: tuple[ComponentLevel, ...] = field(default=(), compare=False)


class Engine(Protocol):
    """Schnittstelle von `TeacherEngine` und `CompiledEngine`."""

    profile: ResolvedProfile
    components: list[ResolvedProfile]

    def level(self, state: State, previous_grades: PreviousGrades = None) -> Decision: ...

    def level_from_grades(
        self,
        grades: Mapping[str, int],
        previous_grades: PreviousGrades = None,
        *,
        missing_safety: bool = False,
    ) -> Decision: ...


def aggregate_value(
    aggregate: AggregateDef, grades: Mapping[str, int], previous: PreviousGrades
) -> int:
    """Wert eines Aggregats (alle monoton in den Graden)."""
    members = [grades[s] for s in aggregate.items]
    kind = aggregate.kind
    if kind == "max_over":
        return max(members, default=0)
    if kind == "min_over":
        return min(members, default=0)
    if kind == "count_ge":
        threshold = aggregate.threshold or 1
        return sum(1 for grade in members if grade >= threshold)
    # trend_flag: irgendein Grad ≥ +1 gegenüber dem letzten Bericht; erster Bericht ⇒ 0.
    if previous is None:
        return 0
    return int(any(grades[s] - previous.get(s, 0) >= 1 for s in aggregate.items))


def _as_composition(source: ResolvedProfile | ResolvedComposition) -> ResolvedComposition:
    return source if isinstance(source, ResolvedComposition) else compose([source], source.id)


class _BaseEngine:
    """Gemeinsame Teile: Komponenten, Grade, Aggregate, Böden, fehlende Safety-Information."""

    def __init__(self, source: ResolvedProfile | ResolvedComposition) -> None:
        self.composition = _as_composition(source)
        self.components: list[ResolvedProfile] = list(self.composition.components)
        self.profile = self.components[0]

    def aggregates_of(
        self, component: ResolvedProfile, grades: Mapping[str, int], previous: PreviousGrades
    ) -> dict[str, int]:
        return {a.id: aggregate_value(a, grades, previous) for a in component.aggregates}

    def fired_rules(
        self, component: ResolvedProfile, aggregates: Mapping[str, int]
    ) -> tuple[list[RuleDef], list[RuleDef]]:
        """`(rote, gelbe)` Lehrerregeln der Komponente, die für diese Aggregatwerte gelten."""
        red = [r for r in component.red_rules if parser.evaluate(r.expr, aggregates)]
        yellow = [r for r in component.yellow_rules if parser.evaluate(r.expr, aggregates)]
        return red, yellow

    def shield_hits(self, grades: Mapping[str, int]) -> tuple[ShieldHit, ...]:
        hits: list[ShieldHit] = []
        for component in self.components:
            env = component.item_env({s: grades.get(s, 0) for s in component.symptoms})
            hits.extend(
                ShieldHit(
                    floor.id,
                    floor.level,
                    tuple(s for s in floor.symptoms if grades.get(s, 0) >= 1),
                )
                for floor in component.floors
                if parser.evaluate(floor.expr, env)
            )
        return tuple(hits)

    def missing_safety(self, state: State) -> tuple[str, ...]:
        """Safety-Symptome ohne jede beantwortete Attribut-Antwort."""
        answered = {symptom for symptom, _attribute in state}
        found: dict[str, None] = {}
        for component in self.components:
            for symptom in component.safety_items:
                if symptom not in answered:
                    found.setdefault(symptom)
        return tuple(found)

    def grades(self, state: State) -> dict[str, int]:
        merged: dict[str, int] = {}
        for component in self.components:
            for symptom, grade in component.grades(state).items():
                merged[symptom] = max(grade, merged.get(symptom, 0))
        return merged

    def level(self, state: State, previous_grades: PreviousGrades = None) -> Decision:
        """`final = max(Komponenten, Böden)`; fehlende Safety-Items ⇒ ≥ YELLOW und `incomplete`."""
        return self.level_from_grades(
            self.grades(state),
            previous_grades,
            missing_safety=bool(self.missing_safety(state)),
        )

    def level_from_grades(
        self,
        grades: Mapping[str, int],
        previous_grades: PreviousGrades = None,
        *,
        missing_safety: bool = False,
    ) -> Decision:
        raise NotImplementedError

    def _finish(
        self,
        levels: list[ComponentLevel],
        rule_reasons: list[Reason],
        grades: Mapping[str, int],
        missing_safety: bool,
        leaves: tuple[LeafRef, ...],
    ) -> Decision:
        hits = self.shield_hits(grades)
        level = max((c.level for c in levels), default=Level.GREEN)
        for hit in hits:
            level = max(level, hit.min_level)
        owner = {f.id: c.id for c in self.components for f in c.floors}
        reasons = [Reason(h.floor_id, owner[h.floor_id], "shield") for h in hits] + rule_reasons
        if missing_safety:
            level = max(level, Level.YELLOW)
            reasons.append(Reason(INCOMPLETE_SAFETY_ITEMS, self.components[0].id, "incomplete"))
        return Decision(
            level,
            tuple(r.code for r in reasons),
            missing_safety,
            hits,
            tuple(reasons),
            leaves,
            tuple(levels),
        )

    def _rule_reasons(
        self, component: ResolvedProfile, aggregates: Mapping[str, int]
    ) -> list[Reason]:
        red, yellow = self.fired_rules(component, aggregates)
        return [Reason(r.id, component.id, "rule") for r in (*red, *yellow)]


class TeacherEngine(_BaseEngine):
    """Wertet Aggregate, Lehrerregeln und Böden direkt aus (Referenz)."""

    def aggregate_value(
        self, aggregate: AggregateDef, grades: Mapping[str, int], previous: PreviousGrades
    ) -> int:
        return aggregate_value(aggregate, grades, previous)

    def aggregates(self, grades: Mapping[str, int], previous: PreviousGrades) -> dict[str, int]:
        return self.aggregates_of(self.profile, grades, previous)

    def teacher_level(self, aggregates: Mapping[str, int]) -> Level:
        """Lehrerlevel der (ersten) Komponente aus Aggregatwerten (Gitterpunkt)."""
        red, yellow = self.fired_rules(self.profile, aggregates)
        if red:
            return Level.RED
        return Level.YELLOW if yellow else Level.GREEN

    def level_from_grades(
        self,
        grades: Mapping[str, int],
        previous_grades: PreviousGrades = None,
        *,
        missing_safety: bool = False,
    ) -> Decision:
        levels: list[ComponentLevel] = []
        reasons: list[Reason] = []
        for component in self.components:
            aggregates = self.aggregates_of(component, grades, previous_grades)
            red, yellow = self.fired_rules(component, aggregates)
            level = Level.RED if red else Level.YELLOW if yellow else Level.GREEN
            levels.append(ComponentLevel(component.id, level))
            reasons.extend(Reason(r.id, component.id, "rule") for r in (*red, *yellow))
        return self._finish(levels, reasons, grades, missing_safety, ())


class CompiledEngine(_BaseEngine):
    """Wertet die kompilierten Bäume aus; Böden und Reason-Codes wie `TeacherEngine`.

    Das Level kommt ausschließlich aus den Bäumen; die Lehrerregeln dienen nur der Erklärung (welche
    Regel-ID gilt). Die Verifikation (`verify.py`) belegt, dass beides übereinstimmt.
    """

    def __init__(
        self,
        source: ResolvedProfile | ResolvedComposition,
        compiled: Sequence[CompiledComponent] | None = None,
    ) -> None:
        super().__init__(source)
        if compiled is None:
            compiled = [compiled_for(c) for c in self.components]
        self.compiled: dict[str, CompiledComponent] = {c.component_id: c for c in compiled}
        for component in self.components:
            if component.id not in self.compiled:
                raise ValueError(f"no compiled component for {component.id}")

    def level_from_grades(
        self,
        grades: Mapping[str, int],
        previous_grades: PreviousGrades = None,
        *,
        missing_safety: bool = False,
    ) -> Decision:
        levels: list[ComponentLevel] = []
        reasons: list[Reason] = []
        leaves: list[LeafRef] = []
        for component in self.components:
            aggregates = self.aggregates_of(component, grades, previous_grades)
            level, yellow_leaf, red_leaf = self.compiled[component.id].classify(aggregates)
            levels.append(ComponentLevel(component.id, level))
            leaves.append(LeafRef(component.id, yellow_leaf, red_leaf))
            reasons.extend(self._rule_reasons(component, aggregates))
        return self._finish(levels, reasons, grades, missing_safety, tuple(leaves))
