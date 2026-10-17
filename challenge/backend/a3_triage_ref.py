"""A3-Referenz für den Triage-Kern (Vertrag v2.0, challenge/contract/triage.md) - unabhängig von A2.

Nur aus der Spezifikation gebaut, ohne Code aus `challenge/backend/waechter`:
- eigener Ausdrucksparser (kein `eval`), Aggregate, Lehrerregeln, Böden, Profilvererbung,
- Gitter-Enumeration über die Aggregatdomänen, Einzelschritt-Nachbarn (Monotonie, inkl. Böden),
- exakte Schranken `lo`/`hi` für unvollständige Zustände und Prüfer für Sitzungsprotokolle.

Die Referenz kennt weder den Baum-Export noch die Auswahlreihenfolge von A2; sie prüft deren
Ergebnisse (`predict(...)`, Protokolle) gegen den Lehrer.
"""

import itertools
import random
import re
from collections.abc import Callable, Collection, Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Final

LEVELS: Final = ("GREEN", "YELLOW", "RED")
RANK: Final = {name: index for index, name in enumerate(LEVELS)}


class TriageError(ValueError):
    """Ladefehler der Wissensbasis (z. B. nicht monotone Lehrerregel)."""


# --- Ausdrucksparser ------------------------------------------------------------------------------

_TOKEN = re.compile(
    r"\s*(?:(?P<num>\d+)|(?P<op><=|>=|==|!=|<|>)|(?P<par>[()])|(?P<name>[A-Za-z_][A-Za-z0-9_.]*))"
)
Node = tuple[Any, ...]


def _tokens(text: str) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    position = 0
    while position < len(text):
        if text[position:].strip() == "":
            break
        match = _TOKEN.match(text, position)
        if match is None or match.end() == position:
            raise TriageError(
                f"unexpected character at {position}: {text[position : position + 10]!r}"
            )
        kind = match.lastgroup or ""
        out.append((kind, match.group(kind)))
        position = match.end()
    return out


class _Parser:
    def __init__(self, text: str) -> None:
        self.tokens = _tokens(text)
        self.index = 0

    def peek(self) -> tuple[str, str] | None:
        return self.tokens[self.index] if self.index < len(self.tokens) else None

    def take(self) -> tuple[str, str]:
        token = self.peek()
        if token is None:
            raise TriageError("unexpected end of expression")
        self.index += 1
        return token

    def parse(self) -> Node:
        node = self.or_()
        if self.peek() is not None:
            raise TriageError(f"trailing tokens: {self.peek()}")
        return node

    def _word(self, word: str) -> bool:
        token = self.peek()
        return token is not None and token[0] == "name" and token[1].lower() == word

    def or_(self) -> Node:
        node = self.and_()
        while self._word("or"):
            self.take()
            node = ("or", node, self.and_())
        return node

    def and_(self) -> Node:
        node = self.not_()
        while self._word("and"):
            self.take()
            node = ("and", node, self.not_())
        return node

    def not_(self) -> Node:
        if self._word("not"):
            self.take()
            return ("not", self.not_())
        return self.cmp()

    def cmp(self) -> Node:
        left = self.atom()
        token = self.peek()
        if token is not None and token[0] == "op":
            self.take()
            return ("cmp", token[1], left, self.atom())
        return left

    def atom(self) -> Node:
        kind, value = self.take()
        if kind == "num":
            return ("num", int(value))
        if kind == "par" and value == "(":
            node = self.or_()
            if self.take() != ("par", ")"):
                raise TriageError("missing )")
            return node
        if kind == "name" and value.lower() not in {"and", "or", "not"}:
            return ("var", value)
        raise TriageError(f"unexpected token {value!r}")


def parse(text: str) -> Node:
    return _Parser(text).parse()


def names_of(node: Node) -> set[str]:
    if node[0] == "var":
        return {str(node[1])}
    return set().union(*(names_of(child) for child in node[1:] if isinstance(child, tuple)), set())


def has_negated_variable(node: Node) -> bool:
    """`not` direkt über einem Vergleich/einer Variablen ⇒ nicht monoton (Spec: Ladefehler)."""
    if node[0] == "not":
        return True
    return any(has_negated_variable(c) for c in node[1:] if isinstance(c, tuple))


def evaluate(node: Node, env: Mapping[str, int]) -> int:
    kind = node[0]
    if kind == "num":
        return int(node[1])
    if kind == "var":
        return int(env[str(node[1])])
    if kind == "not":
        return int(not evaluate(node[1], env))
    if kind == "and":
        return int(bool(evaluate(node[1], env)) and bool(evaluate(node[2], env)))
    if kind == "or":
        return int(bool(evaluate(node[1], env)) or bool(evaluate(node[2], env)))
    if kind == "cmp":
        left, right = evaluate(node[2], env), evaluate(node[3], env)
        return int(
            {"<": left < right, "<=": left <= right, ">": left > right, ">=": left >= right,
             "==": left == right, "!=": left != right}[str(node[1])]
        )  # fmt: skip
    raise TriageError(f"unknown node {kind}")


# --- Wissensbasis ---------------------------------------------------------------------------------


@dataclass(frozen=True)
class Item:
    key: str
    grade_max: int
    critical: bool


@dataclass(frozen=True)
class Aggregate:
    id: str
    kind: str
    items: tuple[str, ...]
    threshold: int | None
    domain_max: int


@dataclass(frozen=True)
class Rule:
    id: str
    when: Node
    level: str  # Lehrer: RED/YELLOW; Boden: min_level


@dataclass
class Profile:
    id: str
    items: dict[str, Item]
    aggregates: list[Aggregate]
    red: list[Rule]
    yellow: list[Rule]
    floors: list[Rule]
    safety_items: set[str] = field(default_factory=set)
    max_questions: int = 12
    grade_map: tuple[int, ...] = (0, 1, 2, 3, 3)


def _aggregate(raw: Mapping[str, Any], items: Mapping[str, Item]) -> Aggregate:
    selector = raw.get("items", "ALL")
    if selector == "ALL":
        keys = tuple(items)
    elif selector == "CRITICAL":
        keys = tuple(k for k, item in items.items() if item.critical)
    else:
        keys = tuple(selector)
    kind = str(raw["kind"])
    top = max((items[k].grade_max for k in keys), default=0)
    domain = {"max_over": top, "min_over": top, "count_ge": len(keys), "trend_flag": 1}[kind]
    return Aggregate(str(raw["id"]), kind, keys, raw.get("threshold"), domain)


def profile_symptoms(kb: Mapping[str, Any], profile_id: str) -> set[str]:
    """Symptome des Profils: feste/Safety-Items, Kaskade, Eskalationsziele, Rotationspool."""
    profiles = {p["id"]: p for p in kb["profiles"]}
    found: set[str] = set()
    current: str | None = profile_id
    while current is not None:
        profile = profiles[current]
        found |= set(profile.get("fixed_items", [])) | set(profile.get("safety_items", []))
        found |= set((profile.get("screening") or {}).get("rotation_pool", []))
        for key, cascade in (profile.get("cascade") or {}).items():
            found.add(key)
            found |= set(cascade.get("escalation_items", []))
        current = profile.get("extends")
    return found


def resolve(kb: Mapping[str, Any], profile_id: str) -> Profile:
    """Profil mit Vererbung `extends` (nur verschärfen: Vereinigung, nichts entfernen)."""
    profiles = {p["id"]: p for p in kb["profiles"]}
    chain: list[Mapping[str, Any]] = []
    current: str | None = profile_id
    while current is not None:
        chain.append(profiles[current])
        current = profiles[current].get("extends")
    chain.reverse()  # Basis zuerst
    items = {
        i["symptom_key"]: Item(i["symptom_key"], int(i["grade_max"]), bool(i["critical"]))
        for i in kb["items"]
    }
    declared = profile_symptoms(kb, profile_id)
    if (
        declared
    ):  # Aggregat ALL/CRITICAL gilt für die Symptome des Profils (Fragebogen der Therapie)
        items = {k: v for k, v in items.items() if k in declared}
    aggregates: dict[str, Mapping[str, Any]] = {}
    red: list[Rule] = []
    yellow: list[Rule] = []
    floors: list[Rule] = []
    safety: set[str] = set()
    max_q = 12
    for profile in chain:
        for raw in profile.get("aggregates", []):
            aggregates[str(raw["id"])] = raw
        for raw in (profile.get("teacher") or {}).get("red", []):
            red.append(Rule(raw["id"], parse(raw["when"]), "RED"))
        for raw in (profile.get("teacher") or {}).get("yellow", []):
            yellow.append(Rule(raw["id"], parse(raw["when"]), "YELLOW"))
        for raw in profile.get("floors", []):
            floors.append(Rule(raw["id"], parse(raw["when"]), str(raw["min_level"]).upper()))
        safety |= set(profile.get("safety_items", []))
        max_q = int((profile.get("screening") or {}).get("max_questions", max_q))
    grade_map = tuple(kb.get("composite_grading", {}).get("map", (0, 1, 2, 3, 3)))
    return Profile(
        profile_id, items, [_aggregate(a, items) for a in aggregates.values()], red, yellow,
        floors, safety, max_q, grade_map,
    )  # fmt: skip


# --- Auswertung -----------------------------------------------------------------------------------


def aggregate_values(
    profile: Profile, grades: Mapping[str, int], trend: Mapping[str, int] | None = None
) -> dict[str, int]:
    """Aggregate aus Itemgraden; `trend` = Vorbericht-Grade je Item (None ⇒ erster Bericht)."""
    out: dict[str, int] = {}
    for agg in profile.aggregates:
        values = [grades.get(k, 0) for k in agg.items]
        if agg.kind == "max_over":
            out[agg.id] = max(values, default=0)
        elif agg.kind == "min_over":
            out[agg.id] = min(values, default=0)
        elif agg.kind == "count_ge":
            out[agg.id] = sum(1 for v in values if v >= int(agg.threshold or 1))
        else:
            prev = trend or {}
            out[agg.id] = int(
                trend is not None and any(grades.get(k, 0) >= prev.get(k, 0) + 1 for k in agg.items)
            )
    return out


def teacher_level(profile: Profile, aggregates: Mapping[str, int]) -> str:
    if any(evaluate(r.when, aggregates) for r in profile.red):
        return "RED"
    if any(evaluate(r.when, aggregates) for r in profile.yellow):
        return "YELLOW"
    return "GREEN"


def item_env(profile: Profile, grades: Mapping[str, int]) -> dict[str, int]:
    env: dict[str, int] = {}
    for key in profile.items:
        grade = grades.get(key, 0)
        env[f"{key}.grade"] = grade
        env[f"{key}.present"] = int(grade > 0)
    return env


def item_env_from(grades: Mapping[str, int]) -> dict[str, int]:
    """`<symptom>.grade`/`.present` aus Graden ohne Profil (für Eskalationsbedingungen)."""
    env: dict[str, int] = {}
    for key, grade in grades.items():
        env[f"{key}.grade"] = grade
        env[f"{key}.present"] = int(grade > 0)
    return env


def floor_level(profile: Profile, grades: Mapping[str, int]) -> str:
    env = item_env(profile, grades)
    best = "GREEN"
    for floor in profile.floors:
        if evaluate(floor.when, env) and RANK[floor.level] > RANK[best]:
            best = floor.level
    return best


def final_level(
    profile: Profile, grades: Mapping[str, int], trend: Mapping[str, int] | None = None
) -> str:
    teacher = teacher_level(profile, aggregate_values(profile, grades, trend))
    return max(teacher, floor_level(profile, grades), key=lambda name: RANK[name])


# --- Gitter, Monotonie, Verifikation --------------------------------------------------------------


def grid(profile: Profile) -> Iterator[dict[str, int]]:
    domains = [range(agg.domain_max + 1) for agg in profile.aggregates]
    for point in itertools.product(*domains):
        yield {agg.id: value for agg, value in zip(profile.aggregates, point, strict=True)}


def grid_size(profile: Profile) -> int:
    size = 1
    for agg in profile.aggregates:
        size *= agg.domain_max + 1
    return size


def check_teacher_monotone(profile: Profile, stride: int = 1) -> list[str]:
    """Lehrerregeln: kein `not`; Einzelschritt-Nachbarn auf dem Aggregatgitter nie sinkend.

    `stride` > 1 prüft nur jeden n-ten Gitterpunkt (mit allen Nachbarn); 1 = vollständig.
    """
    problems = [f"{r.id}: not ist nicht monoton" for r in profile.red + profile.yellow
                if has_negated_variable(r.when)]  # fmt: skip
    for point in itertools.islice(grid(profile), 0, None, stride):
        here = RANK[teacher_level(profile, point)]
        for agg in profile.aggregates:
            if point[agg.id] < agg.domain_max:
                up = {**point, agg.id: point[agg.id] + 1}
                if RANK[teacher_level(profile, up)] < here:
                    problems.append(f"sinkt bei {agg.id}: {point}")
    return problems


@dataclass
class GridReport:
    points: int = 0
    under: int = 0
    over: int = 0
    examples: list[str] = field(default_factory=list)


def compare_on_grid(
    profile: Profile, predict: Callable[[Mapping[str, int]], str], limit: int = 5
) -> GridReport:
    """`predict(aggregates)` (z. B. kompilierter Baum, ohne Böden) gegen den Lehrer, jeder Punkt."""
    report = GridReport()
    for point in grid(profile):
        report.points += 1
        want, got = teacher_level(profile, point), predict(point)
        if RANK[got] < RANK[want]:
            report.under += 1
        elif RANK[got] > RANK[want]:
            report.over += 1
        if got != want and len(report.examples) < limit:
            report.examples.append(f"{point}: Lehrer {want}, Baum {got}")
    return report


def single_step_violations(
    profile: Profile,
    predict: Callable[[Mapping[str, int]], str] | None = None,
    samples: int = 2000,
    seed: int = 1,
) -> list[str]:
    """Einzelschritt-Nachbarn auf dem ITEM-Gitter (inkl. Böden): ein Item +1 senkt das Endlevel nie.

    Ohne `predict` gilt der Lehrer, sonst die Funktion `predict(grades) -> level` des Prüflings.
    Kleine Gitter werden vollständig aufgezählt, größere mit festem Seed gezogen.
    """
    keys = list(profile.items)
    levels = profile.items

    def level(grades: Mapping[str, int]) -> str:
        if predict is None:
            return final_level(profile, grades)
        return predict(grades)

    total = 1
    for key in keys:
        total *= levels[key].grade_max + 1
    if total <= samples * 8:
        states: Iterator[dict[str, int]] = (
            dict(zip(keys, point, strict=True))
            for point in itertools.product(*[range(levels[k].grade_max + 1) for k in keys])
        )
    else:
        rng = random.Random(seed)  # noqa: S311 - fester Seed, kein Krypto
        states = ({k: rng.randint(0, levels[k].grade_max) for k in keys} for _ in range(samples))
    bad: list[str] = []
    for state in states:
        here = RANK[level(state)]
        for key in keys:
            if state[key] < levels[key].grade_max:
                up = {**state, key: state[key] + 1}
                if RANK[level(up)] < here and len(bad) < 10:
                    bad.append(f"{key} {state[key]}→{state[key] + 1} bei {state}")
    return bad


# --- Schranken und Sitzungsprüfer -----------------------------------------------------------------


@dataclass(frozen=True)
class Question:
    symptom_key: str
    attribute: str


def _bounds(
    grade_map: Sequence[int], order: Sequence[str], answers: Mapping[str, int | None]
) -> tuple[int, int]:
    """Grad-Schranken eines Items aus den bisher gegebenen Antworten (Attribut → 0..4 | None).

    Gate (erstes Attribut) = 0 ⇒ Rest gilt als 0. Unbeantwortet: unten mildeste (0), oben schlimmste
    (grade_map[4]). `None` (übersprungen) zählt nicht als Antwort.
    """
    given = {a: v for a, v in answers.items() if v is not None}
    low = max((grade_map[v] for v in given.values()), default=0)
    if order and given.get(order[0]) == 0:
        return 0, 0
    high = grade_map[4] if any(a not in given for a in order) else low
    return low, max(high, low)


@dataclass(frozen=True)
class Escalation:
    """Eskalationsregeln eines Profils: Symptome, die nur bei erfüllter Bedingung gefragt werden."""

    rules: tuple[tuple[Node, tuple[str, ...]], ...]  # (escalate_when, Ziele)
    only: frozenset[str]  # nur über Eskalation fragbar (nicht fest, nicht Safety, nicht Rotation)


def escalation_of(kb: Mapping[str, Any], profile_id: str) -> Escalation:
    profiles = {p["id"]: p for p in kb["profiles"]}
    chain: list[Mapping[str, Any]] = []
    current: str | None = profile_id
    while current is not None:
        chain.append(profiles[current])
        current = profiles[current].get("extends")
    when: dict[str, str] = {}
    targets: dict[str, list[str]] = {}
    fixed: set[str] = set()
    for profile in reversed(chain):  # Basis zuerst; ein Kind darf nur Ziele ergänzen
        fixed |= set(profile.get("fixed_items", [])) | set(profile.get("safety_items", []))
        fixed |= set((profile.get("screening") or {}).get("rotation_pool", []))
        for key, cascade in (profile.get("cascade") or {}).items():
            if cascade.get("escalate_when"):
                when.setdefault(key, cascade["escalate_when"])
            targets.setdefault(key, []).extend(cascade.get("escalation_items", []))
    rules = tuple((parse(when[k]), tuple(t)) for k, t in targets.items() if t and k in when)
    every = {t for items in targets.values() for t in items}
    return Escalation(rules, frozenset(every - fixed))


def level_bounds(
    profile: Profile,
    cascade: Mapping[str, Sequence[str]],
    given: Mapping[str, Mapping[str, int | None]],
    askable: Collection[str] | None = None,
    escalation: Escalation | None = None,
    previous: Mapping[str, int] | None = None,
) -> tuple[str, str]:
    """`(lo, hi)`: Endlevel, Unbeantwortetes mildest bzw. schlimmstmöglich (inkl. Böden).

    `askable`: Symptome, die in dieser Sitzung überhaupt gefragt werden können (z. B. ohne die nicht
    aktiven Rotationssymptome); andere zählen 0/0. `escalation`: Symptome, die nur bei erfüllter
    Bedingung gefragt werden, zählen oben erst, wenn die Bedingung bei den schlimmsten Graden der
    übrigen Symptome erfüllbar ist (Fixpunkt); beantwortete zählen immer.
    """
    lows: dict[str, int] = {}
    highs: dict[str, int] = {}
    worst: dict[str, int] = {}
    for key, item in profile.items.items():
        if askable is not None and key not in askable:
            lows[key] = highs[key] = worst[key] = 0
            continue
        order = cascade.get(key, ["severity"])
        low, high = _bounds(profile.grade_map, order, given.get(key, {}))
        lows[key] = min(low, item.grade_max)
        worst[key] = highs[key] = min(high, item.grade_max)
    if escalation is not None:
        locked = {k for k in escalation.only if not given.get(k)}
        for key in locked:
            highs[key] = lows[key]
        changed = True
        while changed:
            changed = False
            env = item_env(profile, highs)
            for expr, targets in escalation.rules:
                if evaluate(expr, env):
                    for target in targets:
                        if target in locked:
                            locked.discard(target)
                            highs[target] = worst[target]
                            changed = True
    return final_level(profile, lows, previous), final_level(profile, highs, previous)


@dataclass
class Step:
    question: Question
    value: int | None


@dataclass
class Transcript:
    steps: list[Step]
    stop_reason: str  # decided | burden_cap | complete
    incomplete: bool
    level: str | None = None


def check_transcript(
    profile: Profile,
    cascade: Mapping[str, Sequence[str]],
    transcript: Transcript,
    truth: Mapping[str, int],
    askable: Collection[str] | None = None,
    escalation: Escalation | None = None,
    previous: Mapping[str, int] | None = None,
) -> list[str]:
    """Prüft ein Sitzungsprotokoll gegen die Lehrer-Schranken; liefert Verstöße (leer = in Ordnung).

    `truth` = wahre Itemgrade der Patientin (für Antworten > Gate; Gate=0 ⇒ Item 0).
    """
    problems: list[str] = []
    seen: set[Question] = set()
    given: dict[str, dict[str, int | None]] = {}
    last_lo, last_hi = level_bounds(profile, cascade, given, askable, escalation, previous)
    for index, step in enumerate(transcript.steps, 1):
        question = step.question
        if question in seen:
            problems.append(f"Frage {question} doppelt (Schritt {index})")
        seen.add(question)
        given.setdefault(question.symptom_key, {})[question.attribute] = step.value
        lo, hi = level_bounds(profile, cascade, given, askable, escalation, previous)
        if RANK[lo] < RANK[last_lo]:
            problems.append(f"lo sinkt bei Schritt {index}: {last_lo}→{lo}")
        if RANK[hi] > RANK[last_hi]:
            problems.append(f"hi steigt bei Schritt {index}: {last_hi}→{hi}")
        last_lo, last_hi = lo, hi
        if lo == hi and index < len(transcript.steps):
            unanswered_safety = [
                s for s in profile.safety_items if not any(q.symptom_key == s for q in seen)
            ]
            if not unanswered_safety:
                problems.append(f"Frage nach entschiedenem Zustand (Schritt {index + 1})")
    if len(transcript.steps) > profile.max_questions:
        problems.append("mehr Fragen als max_questions")
    if transcript.stop_reason == "decided" and last_lo != last_hi:
        problems.append(f"Stopp 'decided' bei lo {last_lo} ≠ hi {last_hi}")
    if transcript.stop_reason == "burden_cap" and (last_lo != last_hi) != transcript.incomplete:
        problems.append("incomplete passt nicht zu lo/hi bei burden_cap")
    unanswered_safety = [
        s for s in profile.safety_items if not any(q.symptom_key == s for q in seen)
    ]
    if unanswered_safety and not transcript.incomplete:
        problems.append(f"Safety-Items ohne Antwort ohne incomplete: {unanswered_safety}")
    if transcript.stop_reason == "decided" and last_lo == last_hi:
        want = final_level(profile, truth, previous)
        if RANK[last_lo] < RANK[want]:
            problems.append(f"Untertriage: angezeigt {last_lo}, wahr {want}")
    return problems


# --- Empfehlungsregeln ADV-xx (Vertrag v2.1 §6) ---

ADV_ID = re.compile(r"^ADV-[A-Z0-9_]+-[0-9]{2}$")


@dataclass(frozen=True)
class AdviceRule:
    id: str
    symptom_key: str
    min_value: int
    max_value: int = 4


def advice_rules_from(advice: Mapping[str, Any]) -> list[AdviceRule]:
    """Regeln aus `advice.yaml` (je Regel id, symptom_key, min_value, max_value)."""
    return [
        AdviceRule(
            str(r["id"]), str(r["symptom_key"]), int(r["min_value"]), int(r.get("max_value", 4))
        )
        for r in advice["advice"]
    ]


def check_advice_rules(rules: Sequence[AdviceRule]) -> list[str]:
    """Formfehler: ID-Muster (`ADV-<SYMPTOM>-NN` passend zum Symptom), eindeutig, Bereich 0..4."""
    problems: list[str] = []
    seen: set[str] = set()
    for rule in rules:
        if not ADV_ID.match(rule.id):
            problems.append(f"{rule.id}: ID-Muster")
        elif rule.id.split("-")[1:-1] != [rule.symptom_key.upper()]:
            problems.append(f"{rule.id}: ID nennt nicht das Symptom {rule.symptom_key}")
        if rule.id in seen:
            problems.append(f"{rule.id}: doppelt")
        seen.add(rule.id)
        if not 0 <= rule.min_value <= rule.max_value <= 4:
            problems.append(f"{rule.id}: Bereich [{rule.min_value},{rule.max_value}]")
    return problems


def advice_fires(rule: AdviceRule, answers: Mapping[str, int | None]) -> bool:
    """Feuert, wenn irgendein beantwortetes Attribut des Symptoms im Bereich liegt."""
    return any(v is not None and rule.min_value <= v <= rule.max_value for v in answers.values())


def evaluate_recommendations(
    rules: Sequence[AdviceRule],
    answers: Mapping[str, Mapping[str, int | None]],
    red_symptoms: set[str],
    always_acute_for: set[str],
) -> dict[str, str]:
    """`{regel_id: shown | suppressed_acute}` für alle feuernden Regeln (alle passenden gelten)."""
    out: dict[str, str] = {}
    for rule in rules:
        if not advice_fires(rule, answers.get(rule.symptom_key, {})):
            continue
        suppressed = rule.symptom_key in red_symptoms or rule.symptom_key in always_acute_for
        out[rule.id] = "suppressed_acute" if suppressed else "shown"
    return out


def check_recommendations(
    rules: Sequence[AdviceRule],
    answers: Mapping[str, Mapping[str, int | None]],
    red_symptoms: set[str],
    always_acute_for: set[str],
    observed: Mapping[str, str],
    patient_rule_ids: Sequence[str] | None = None,
) -> list[str]:
    """Vergleicht das Ergebnis der Implementierung (`observed`) mit der Referenz.

    `patient_rule_ids` = IDs in `SubmitReceipt.advice[]`: nur `shown`-Regeln, nie unterdrückte.
    """
    want = evaluate_recommendations(rules, answers, red_symptoms, always_acute_for)
    problems = [
        f"{rule_id}: erwartet {status}, beobachtet {observed.get(rule_id, 'fehlt')}"
        for rule_id, status in want.items()
        if observed.get(rule_id) != status
    ]
    problems += [
        f"{rule_id}: feuert nicht, wurde aber ausgegeben"
        for rule_id in observed
        if rule_id not in want
    ]
    if patient_rule_ids is not None:
        shown = {rule_id for rule_id, status in want.items() if status == "shown"}
        if set(patient_rule_ids) != shown:
            problems.append(f"Patientin sieht {sorted(patient_rule_ids)}, erwartet {sorted(shown)}")
    return problems


# --- Domänenkompression (Vertrag v2.2 H3) ---


def _constants(node: Node, found: dict[str, int | None], names: set[str]) -> None:
    """Sammelt je Variable die größte Vergleichskonstante; `None` = nicht kompressibel."""
    kind = node[0]
    if kind == "cmp":
        left, right = node[2], node[3]
        if left[0] == "var" and right[0] == "num":
            _note(found, str(left[1]), int(right[1]))
        elif left[0] == "num" and right[0] == "var":
            _note(found, str(right[1]), int(left[1]))
        else:  # Variable gegen Variable / Ausdruck: keine Kürzung
            for child in (left, right):
                if child[0] == "var":
                    found[str(child[1])] = None
                else:
                    _constants(child, found, names)
        return
    if kind == "var":  # bloße Variable = Vergleich mit 0
        _note(found, str(node[1]), 0)
        return
    for child in node[1:]:
        if isinstance(child, tuple):
            _constants(child, found, names)


def _note(found: dict[str, int | None], name: str, constant: int) -> None:
    if name in found and found[name] is None:
        return
    found[name] = max(constant, found.get(name) or 0)


def compressed_domains(profile: Profile) -> dict[str, int]:
    """Domänenmaximum je Aggregat nach Kompression: `min(natürliches Maximum, k_max + 1)`."""
    found: dict[str, int | None] = {}
    for rule in profile.red + profile.yellow:
        _constants(rule.when, found, set())
    out: dict[str, int] = {}
    for agg in profile.aggregates:
        k_max = found.get(agg.id, 0)
        out[agg.id] = agg.domain_max if k_max is None else min(agg.domain_max, k_max + 1)
    return out


def check_compression(profile: Profile, stride: int = 1) -> list[str]:
    """Regelergebnisse auf dem UNGEKÜRZTEN Gitter == Ergebnisse nach Kürzung jedes Aggregatwerts."""
    caps = compressed_domains(profile)
    bad: list[str] = []
    for point in itertools.islice(grid(profile), 0, None, stride):
        squeezed = {k: min(v, caps[k]) for k, v in point.items()}
        if teacher_level(profile, point) != teacher_level(profile, squeezed) and len(bad) < 10:
            bad.append(f"{point} -> {squeezed}")
    return bad


def compressed_size(profile: Profile) -> int:
    size = 1
    for cap in compressed_domains(profile).values():
        size *= cap + 1
    return size
