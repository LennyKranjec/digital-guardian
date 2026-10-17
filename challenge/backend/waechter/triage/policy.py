"""Selection Policy (Vertrag triage.md §3): Schranken, Gate/Kaskade, FlipPolicy, rotierende Slots.

Reine, deterministische Funktionen über `(State, asked)`. Jede Engine, die `Engine` erfüllt, genügt
(`TeacherEngine`, später `CompiledEngine`).

Reihenfolge von `next_question`:
1. unbeantwortete Safety-Items (immer, auch bei `decided`; sie stehen vor dem Fragenlimit),
2. `lo == hi` ⇒ Stopp `decided`,
3. Fragenzähler ≥ `max_questions` ⇒ Stopp `burden_cap`,
4. offene Kaskade eines Symptoms mit Gate > 0 (feste Reihenfolge aus der Wissensbasis),
5. Gate-Fragen nach FlipPolicy `(red_flag, flips, priority, -burden)`, Tie-Break Symptomschlüssel,
6. nichts mehr zu fragen ⇒ Stopp `complete`.

Schranken: unbeantwortete, **fragbare** Felder auf mildeste (0) bzw. schlimmste Antwort; Gate = 0 ⇒
Folgeattribute werden nicht gefragt und gelten als 0; Folgefragen eines Symptoms, dessen Grad schon
`grade_max` ist, entfallen. Unbeantwortete Safety-Items heben die obere Schranke mindestens auf
YELLOW an (wie das Endlevel). Es gilt `lo ≤ level(state) ≤ hi` und, weil die Engine monoton ist,
`lo == hi` ⇒ keine weitere Antwort ändert das Level.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Literal

from waechter.triage import parser
from waechter.triage.engine import Engine, PreviousGrades
from waechter.triage.kb import Key, Level, ResolvedProfile, State

type Role = Literal["safety", "fixed", "escalation", "rotating"]


class QuestionKind(StrEnum):
    SAFETY = "safety"
    GATE = "gate"
    CASCADE = "cascade"
    ESCALATION = "escalation"
    ROTATING = "rotating"


@dataclass(frozen=True)
class Question:
    symptom_key: str
    attribute: str
    kind: QuestionKind
    red_flag: bool
    flips: bool


@dataclass(frozen=True)
class Stop:
    reason: Literal["decided", "burden_cap", "complete"]
    incomplete: bool
    level_lo: Level
    level_hi: Level


@dataclass(frozen=True)
class Bounds:
    lo: Level
    hi: Level


@dataclass(frozen=True)
class _Plan:
    roles: dict[str, Role]
    open_fields: tuple[Key, ...]
    hi_state: dict[Key, int]


class FlipPolicy:
    """Standard-Reihenfolge der Fragen (deterministisch)."""

    def __init__(self, engine: Engine) -> None:
        self.engine = engine
        self.profile: ResolvedProfile = engine.profile

    # ---- Struktur der Sitzung -----------------------------------------------------------------
    def rotating_symptoms(self, cycle_week: int) -> tuple[str, ...]:
        """Round-Robin über die Zykluswoche: `rotating_slots` Symptome des Pools je Woche."""
        pool = [s for s in self.profile.rotation_pool if s not in self.profile.fixed_items]
        slots = min(self.profile.rotating_slots, len(pool))
        if slots == 0:
            return ()
        start = (cycle_week * slots) % len(pool)
        return tuple(pool[(start + i) % len(pool)] for i in range(slots))

    def _gate_grade(self, symptom: str, value: int) -> int:
        item = self.profile.items[symptom]
        return min(self.profile.grade_map[value], item.grade_max)

    def _open_for(
        self, symptom: str, role: Role, state: State, grades: Mapping[str, int]
    ) -> list[Key]:
        profile = self.profile
        if grades[symptom] >= profile.items[symptom].grade_max:
            return []
        attributes = profile.order(symptom)
        gate = attributes[0]
        if (symptom, gate) in state:
            if role == "rotating" or self._gate_grade(symptom, state[(symptom, gate)]) == 0:
                return []
            return [(symptom, a) for a in attributes[1:] if (symptom, a) not in state]
        if role == "rotating":
            return [(symptom, gate)]
        return [(symptom, a) for a in attributes if (symptom, a) not in state]

    def _open_fields(self, roles: Mapping[str, Role], state: State) -> list[Key]:
        grades = self.profile.grades(state)
        fields: list[Key] = []
        for symptom, role in roles.items():
            fields.extend(self._open_for(symptom, role, state, grades))
        return fields

    def _plan(self, state: State, cycle_week: int) -> _Plan:
        profile = self.profile
        roles: dict[str, Role] = dict.fromkeys(profile.fixed_items, "fixed")
        roles.update(dict.fromkeys(profile.safety_items, "safety"))
        for symptom in self.rotating_symptoms(cycle_week):
            roles.setdefault(symptom, "rotating")
        while True:
            fields = self._open_fields(roles, state)
            hi_state = dict(state)
            hi_state.update({f: profile.max_value(f[1]) for f in fields})
            env = profile.item_env(profile.grades(hi_state))
            changed = False
            for symptom, role in list(roles.items()):
                cascade = profile.cascade.get(symptom)
                if role == "rotating" or cascade is None or cascade.escalate_expr is None:
                    continue
                if not parser.evaluate(cascade.escalate_expr, env):
                    continue
                for target in cascade.escalation_items:
                    if roles.get(target) in (None, "rotating"):
                        roles[target] = "escalation"
                        changed = True
            if not changed:
                return _Plan(roles, tuple(fields), hi_state)

    def session_symptoms(self, cycle_week: int = 0) -> tuple[str, ...]:
        """Alle Symptome, die in einer Sitzung dieser Woche überhaupt gefragt werden können."""
        return tuple(self._plan({}, cycle_week).roles)

    def open_fields(self, state: State, cycle_week: int = 0) -> tuple[Key, ...]:
        """Alle unbeantworteten, noch fragbaren Felder dieser Sitzung (Grundlage der Schranken)."""
        return self._plan(state, cycle_week).open_fields

    # ---- Schranken ----------------------------------------------------------------------------
    def _missing_safety(self, state: State) -> bool:
        answered = {symptom for symptom, _attribute in state}
        return any(s not in answered for s in self.profile.safety_items)

    def _bounds(self, plan: _Plan, state: State, previous_grades: PreviousGrades) -> Bounds:
        lo_state = dict(state)
        lo_state.update(dict.fromkeys(plan.open_fields, 0))
        lo = self.engine.level(lo_state, previous_grades).level
        hi = self.engine.level(plan.hi_state, previous_grades).level
        if self._missing_safety(state):
            hi = max(hi, Level.YELLOW)
        return Bounds(lo, hi)

    def bounds(
        self, state: State, previous_grades: PreviousGrades = None, cycle_week: int = 0
    ) -> Bounds:
        """`lo`/`hi`: Level bei mildester bzw. schlimmster Antwort aller offenen Felder."""
        return self._bounds(self._plan(state, cycle_week), state, previous_grades)

    # ---- Nächste Frage ------------------------------------------------------------------------
    def _flips(
        self, state: State, symptom: str, attribute: str, base: Level, previous: PreviousGrades
    ) -> bool:
        for value in range(self.profile.max_value(attribute) + 1):
            trial = dict(state)
            trial[(symptom, attribute)] = value
            if self.engine.level(trial, previous).level != base:
                return True
        return False

    def _unlocked(self, plan: _Plan, grades: Mapping[str, int]) -> set[str]:
        """Eskalations-Symptome, deren `escalate_when` für den aktuellen State erfüllt ist."""
        profile = self.profile
        env = profile.item_env(grades)
        found: set[str] = set()
        for symptom, role in plan.roles.items():
            cascade = profile.cascade.get(symptom)
            if role == "rotating" or cascade is None or cascade.escalate_expr is None:
                continue
            if parser.evaluate(cascade.escalate_expr, env):
                found.update(cascade.escalation_items)
        return found

    def next_question(
        self,
        state: State,
        asked: Sequence[Key] = (),
        previous_grades: PreviousGrades = None,
        cycle_week: int = 0,
    ) -> Question | Stop:
        """Nächste Frage oder Stopp (`decided`, `burden_cap`, `complete`).

        `asked`: bisher gestellte Felder in Reihenfolge (auch übersprungene, die nicht im State
        stehen). Beantwortete Felder zählen immer als gestellt.
        """
        profile = self.profile
        plan = self._plan(state, cycle_week)
        asked_set = set(asked) | set(state)
        answered = {symptom for symptom, _attribute in state}
        grades = profile.grades(state)
        decision = self.engine.level(state, previous_grades)

        for symptom in profile.safety_items:
            gate = profile.order(symptom)[0]
            if symptom not in answered and (symptom, gate) not in asked_set:
                flips = self._flips(state, symptom, gate, decision.level, previous_grades)
                return Question(symptom, gate, QuestionKind.SAFETY, True, flips)

        bounds = self._bounds(plan, state, previous_grades)
        incomplete = decision.incomplete or bounds.lo < bounds.hi
        if bounds.lo == bounds.hi:
            return Stop("decided", decision.incomplete, bounds.lo, bounds.hi)
        if len(asked_set) >= profile.max_questions:
            return Stop("burden_cap", incomplete, bounds.lo, bounds.hi)

        cascade_question = self._pending_cascade(plan, state, asked, asked_set, grades)
        if cascade_question is not None:
            return cascade_question

        unlocked = self._unlocked(plan, grades)
        candidates: list[Question] = []
        for symptom, role in plan.roles.items():
            gate = profile.order(symptom)[0]
            if symptom in answered or (symptom, gate) in asked_set:
                continue
            if role == "escalation" and symptom not in unlocked:
                continue
            kind = {
                "safety": QuestionKind.SAFETY,
                "fixed": QuestionKind.GATE,
                "escalation": QuestionKind.ESCALATION,
                "rotating": QuestionKind.ROTATING,
            }[role]
            flips = self._flips(state, symptom, gate, decision.level, previous_grades)
            candidates.append(
                Question(symptom, gate, kind, symptom in profile.red_flag_symptoms, flips)
            )
        if not candidates:
            return Stop("complete", incomplete, bounds.lo, bounds.hi)
        decisive = [q for q in candidates if q.red_flag or q.flips] or candidates

        def order(question: Question) -> tuple[bool, bool, float, float, str]:
            symptom = question.symptom_key
            return (
                not question.red_flag,
                not question.flips,
                -profile.priority.get(symptom, 0.0),
                profile.items[symptom].burden,
                symptom,
            )

        return min(decisive, key=order)

    def _pending_cascade(
        self,
        plan: _Plan,
        state: State,
        asked: Sequence[Key],
        asked_set: set[Key],
        grades: Mapping[str, int],
    ) -> Question | None:
        profile = self.profile
        position = {key: index for index, key in enumerate(asked)}
        pending: list[tuple[int, int, Question]] = []
        for rank, (symptom, role) in enumerate(plan.roles.items()):
            if role == "rotating" or grades[symptom] >= profile.items[symptom].grade_max:
                continue
            attributes = profile.order(symptom)
            gate_key = (symptom, attributes[0])
            if gate_key not in state or self._gate_grade(symptom, state[gate_key]) == 0:
                continue
            for attribute in attributes[1:]:
                if (symptom, attribute) not in asked_set:
                    question = Question(
                        symptom,
                        attribute,
                        QuestionKind.CASCADE,
                        symptom in profile.red_flag_symptoms,
                        False,
                    )
                    pending.append((position.get(gate_key, -1), rank, question))
                    break
        if not pending:
            return None
        return min(pending, key=lambda entry: (entry[0], entry[1]))[2]
