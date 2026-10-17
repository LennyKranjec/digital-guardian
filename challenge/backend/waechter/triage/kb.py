"""Triage-Wissensbasis: Lader, Schemaprüfung, Querverweise, Vererbung „nur verschärfen“, Hash.

Quelle: `challenge/content/triage.yaml` (Schema `content.schema.json#/$defs/TriageFile`, Vertrag
`challenge/contract/triage.md` §2). Alle klinischen Inhalte sind Platzhalter mit `assumption`.

Der Lader prüft in dieser Reihenfolge: (1) YAML, (2) Schema mit dem eigenen Prüfer, (3) Querverweise
(Symptome gegen `items.yaml`, Regime gegen `regimens.yaml`, Annahmen), (4) Vererbung (Lockerung ohne
`loosening`-Block ist ein Fehler), (5) je Blattprofil: Ausdrücke parsen, Namen prüfen, Lehrerregeln,
Böden und Eskalationsbedingungen auf Monotonie prüfen (Einzelschritt-Nachbarn auf dem Gitter),
`not` auf Aggregaten verbieten. Fehler nennen Pfad und Regel-ID, nie Antwortwerte.
"""

import copy
import hashlib
import itertools
import json
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass, field
from enum import IntEnum
from pathlib import Path
from typing import Any, Final

import yaml

from waechter import schema_check
from waechter.content import SCHEMA_PATH, content_dir, load_content
from waechter.triage import parser

TRIAGE_FILE: Final = "triage.yaml"
STATUS_ORDER: Final = ("placeholder", "draft", "reviewed", "approved")
MAX_GRID_POINTS: Final = 200_000
#: Wertebereich einer gespeicherten Antwort (presence: 0/1, sonst 0..4)
ANSWER_MAX: Final = 4
PRESENCE_MAX: Final = 1

type Key = tuple[str, str]
type State = Mapping[Key, int]


class Level(IntEnum):
    GREEN = 0
    YELLOW = 1
    RED = 2


@dataclass(frozen=True)
class TriageIssue:
    path: str
    message: str

    def __str__(self) -> str:
        return f"{TRIAGE_FILE}: {self.path}: {self.message}"


class TriageError(ValueError):
    """Wissensbasis fehlt, ist kein YAML oder verletzt Schema, Querverweise, Sicherheitsregeln."""

    def __init__(self, issues: Sequence[TriageIssue]) -> None:
        self.issues = list(issues)
        super().__init__("; ".join(str(i) for i in self.issues))


@dataclass(frozen=True)
class ItemDef:
    symptom_key: str
    grade_max: int
    critical: bool
    origin: str
    burden: float
    attributes: tuple[str, ...]


@dataclass(frozen=True)
class AggregateDef:
    id: str
    kind: str
    items: tuple[str, ...]
    threshold: int | None
    max_value: int
    label: Mapping[str, str] | None = None


@dataclass(frozen=True)
class RuleDef:
    """Lehrerregel (`level` = RED/YELLOW) oder Boden (`level` = `min_level`, `locked`)."""

    id: str
    when: str
    expr: parser.Expr
    level: Level
    status: str
    source: str | None
    assumption: str | None
    text: Mapping[str, str] | None
    symptoms: tuple[str, ...] = ()
    locked: bool = False
    loosened: bool = False


@dataclass(frozen=True)
class CascadeDef:
    symptom_key: str
    attributes_order: tuple[str, ...]
    escalate_when: str | None
    escalate_expr: parser.Expr | None
    escalation_items: tuple[str, ...]


@dataclass(frozen=True, eq=False)
class ResolvedProfile:
    id: str
    lineage: tuple[str, ...]
    status: str
    symptoms: tuple[str, ...]
    fixed_items: tuple[str, ...]
    safety_items: tuple[str, ...]
    rotation_pool: tuple[str, ...]
    rotating_slots: int
    max_questions: int
    items: Mapping[str, ItemDef]
    grade_map: tuple[int, ...]
    cascade: Mapping[str, CascadeDef]
    aggregates: tuple[AggregateDef, ...]
    red_rules: tuple[RuleDef, ...]
    yellow_rules: tuple[RuleDef, ...]
    floors: tuple[RuleDef, ...]
    priority: Mapping[str, float]
    loosened: tuple[str, ...]
    hash: str
    regimen_ids: tuple[str, ...] = ()

    def order(self, symptom: str) -> tuple[str, ...]:
        """Attribut-Reihenfolge der Fragen (erstes = Gate); ohne Kaskade die der Items-Datei."""
        cascade = self.cascade.get(symptom)
        return cascade.attributes_order if cascade else self.items[symptom].attributes

    @property
    def red_flag_symptoms(self) -> frozenset[str]:
        """Safety-Items und alle Symptome, die ein Boden liest."""
        found = set(self.safety_items)
        for floor in self.floors:
            found.update(floor.symptoms)
        return frozenset(found)

    @property
    def full_question_count(self) -> int:
        """Anzahl aller Attribut-Felder der Symptome des Profils (Vollset-Vergleich)."""
        return sum(len(self.order(s)) for s in self.symptoms)

    def grades(self, state: State) -> dict[str, int]:
        """Symptomgrade (Composite): `max` über `grade_map[v]` beantworteter Attribute, gedeckelt.

        Unbeantwortet = 0. Antworten zu Symptomen außerhalb des Profils bleiben unberücksichtigt;
        ungültige Attribute oder Werte sind ein `ValueError` (der Aufrufer validiert zuvor).
        """
        grades = dict.fromkeys(self.symptoms, 0)
        for (symptom, attribute), value in state.items():
            item = self.items.get(symptom)
            if item is None:
                continue
            if attribute not in item.attributes:
                raise ValueError("unknown attribute")
            limit = PRESENCE_MAX if attribute == "presence" else ANSWER_MAX
            if isinstance(value, bool) or not 0 <= value <= limit:
                raise ValueError("answer value out of range")
            grade = min(self.grade_map[value], item.grade_max)
            if grade > grades[symptom]:
                grades[symptom] = grade
        return grades

    def item_env(self, grades: Mapping[str, int]) -> dict[str, int]:
        """Variablen für Böden und Eskalationsbedingungen: `<symptom>.grade` und `.present`."""
        env: dict[str, int] = {}
        for symptom, grade in grades.items():
            env[f"{symptom}.grade"] = grade
            env[f"{symptom}.present"] = int(grade >= 1)
        return env

    def max_value(self, attribute: str) -> int:
        return PRESENCE_MAX if attribute == "presence" else ANSWER_MAX


@dataclass(frozen=True, eq=False)
class ResolvedComposition:
    """Aufgelöste Zusammensetzung eines Profils aus Komponenten (Delta v2.1, Hook H1).

    Heute besteht jede Zusammensetzung aus **genau einer** Komponente = dem bisherigen Profil
    (`includes` ist leer erzwungen); `composition_hash` ist dann der Profil-Hash, Verhalten und Hash
    bestehender Profile bleiben unverändert. Module und Wirkstoffkatalog sind bewusst nicht gebaut.
    """

    id: str
    components: tuple[ResolvedProfile, ...]
    items: Mapping[str, ItemDef]
    max_questions: int
    q_worst_total: int
    coverage_gap: bool
    composition_status: str
    composition_hash: str


def compose(components: Sequence[ResolvedProfile], composition_id: str) -> ResolvedComposition:
    """Zusammensetzung aus Komponenten; bei einer Komponente identisch zum Profil."""
    items: dict[str, ItemDef] = {}
    for component in components:
        items.update(component.items)
    single = len(components) == 1
    return ResolvedComposition(
        id=composition_id,
        components=tuple(components),
        items=items,
        max_questions=max(c.max_questions for c in components),
        q_worst_total=sum(c.full_question_count for c in components),
        coverage_gap=False,
        composition_status=min((c.status for c in components), key=STATUS_ORDER.index),
        composition_hash=components[0].hash
        if single
        else canonical_hash([c.hash for c in components]),
    )


@dataclass(frozen=True, eq=False)
class KnowledgeBase:
    version: str
    hash: str
    composite_map: tuple[int, ...]
    profiles: Mapping[str, ResolvedProfile]
    regimen_profile: Mapping[str, str]
    assumptions: Mapping[str, Mapping[str, str]]
    raw: Mapping[str, Any] = field(repr=False, default_factory=dict)
    # T-24 (PoC Module): Profile mit `includes` (Klassenmodule) und Varianten `<Blatt>+<Modul>`.
    # Bewusst getrennt von `profiles`: bestehende Profile, Hashes und Prüfläufe bleiben unverändert.
    compositions: Mapping[str, ResolvedProfile] = field(default_factory=dict)
    diagnosis_modules: Mapping[str, str] = field(default_factory=dict)  # Diagnosegruppe ⇒ Modul

    def profile(self, profile_id: str) -> ResolvedProfile:
        found = self.find(profile_id)
        if found is None:
            raise KeyError(profile_id)
        return found

    def find(self, profile_id: str) -> ResolvedProfile | None:
        return self.profiles.get(profile_id) or self.compositions.get(profile_id)

    def resolve(self, profile_id: str) -> ResolvedComposition:
        """Zusammensetzung des Profils; Module sind beim Auflösen eingeflochten."""
        return compose([self.profile(profile_id)], profile_id)

    def variant_for(self, profile_id: str, diagnosis_group_id: str | None) -> str:
        """Profil-ID inkl. Diagnosemodul der Gruppe (T-24), sonst unverändert."""
        module = self.diagnosis_modules.get(diagnosis_group_id or "")
        variant = f"{profile_id}+{module}" if module else profile_id
        return variant if variant in self.compositions else profile_id

    def profile_for_regimen(self, regimen_id: str) -> ResolvedProfile:
        return self.profiles[self.regimen_profile[regimen_id]]


def canonical_hash(document: Any) -> str:
    """SHA-256 über die kanonische JSON-Form (sortierte Schlüssel, kompakt, UTF-8)."""
    text = json.dumps(document, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _triage_schema() -> tuple[dict[str, Any], dict[str, Any]]:
    """`(root, TriageFile)`; `oneOf` (nicht vom eigenen Prüfer unterstützt) wird ersetzt.

    Die betroffene Stelle ist `aggregates[].items` (`ALL`/`CRITICAL` oder Liste): `_aggregate_items`
    prüft sie ersatzweise ausdrücklich.
    """
    root: dict[str, Any] = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    definition = copy.deepcopy(root["$defs"]["TriageFile"])

    def strip(node: Any) -> None:
        if isinstance(node, dict):
            node.pop("oneOf", None)
            for value in node.values():
                strip(value)
        elif isinstance(node, list):
            for value in node:
                strip(value)

    strip(definition)
    # Hook H1 (triage.md §7): `includes` = Liste von Modul-IDs, derzeit leer erzwungen.
    # T-24: `includes` und `modules` sind im Schema selbst definiert (Klassen- und Diagnosemodule).
    return root, definition


class _Issues:
    def __init__(self) -> None:
        self._found: dict[tuple[str, str], None] = {}

    def add(self, path: str, message: str) -> None:
        self._found.setdefault((path, message))

    def __bool__(self) -> bool:
        return bool(self._found)

    def all(self) -> list[TriageIssue]:
        return [TriageIssue(path, message) for path, message in self._found]


def _one_of(raw: Mapping[str, Any], path: str, issues: _Issues) -> bool:
    """Genau eins von `source`/`assumption` (Herkunft jeder Regel und Zahl)."""
    has_source, has_assumption = "source" in raw, "assumption" in raw
    if has_source == has_assumption:
        issues.add(path, "exactly one of source/assumption is required")
        return False
    return True


@dataclass
class _Merged:
    """Zusammengeführte Rohdaten entlang der Vererbungskette (Wurzel → Blatt)."""

    fixed: list[str] = field(default_factory=list)
    safety: list[str] = field(default_factory=list)
    pool: list[str] = field(default_factory=list)
    max_questions: int | None = None
    rotating_slots: int = 0
    cascade: dict[str, dict[str, Any]] = field(default_factory=dict)
    aggregates: dict[str, dict[str, Any]] = field(default_factory=dict)
    rules: dict[str, tuple[str, dict[str, Any], str]] = field(default_factory=dict)
    priority: dict[str, float] = field(default_factory=dict)
    loosened: list[str] = field(default_factory=list)

    def document(self, lineage: Sequence[str]) -> dict[str, Any]:
        """JSON-fähige Form für den Profil-Hash."""
        return {
            "lineage": list(lineage),
            "fixed": self.fixed,
            "safety": self.safety,
            "pool": self.pool,
            "max_questions": self.max_questions,
            "rotating_slots": self.rotating_slots,
            "cascade": self.cascade,
            "aggregates": self.aggregates,
            "rules": {k: [kind, raw] for k, (kind, raw, _origin) in self.rules.items()},
            "priority": self.priority,
            "loosened": self.loosened,
        }


def _extend(target: list[str], values: Sequence[str]) -> None:
    for value in values:
        if value not in target:
            target.append(value)


class _Builder:
    def __init__(
        self,
        raw: Mapping[str, Any],
        attributes: Mapping[str, Sequence[str]],
        regimens: Mapping[str, Collection[str]],
    ) -> None:
        self.raw = raw
        self.attributes = attributes
        self.regimens = regimens
        self.issues = _Issues()
        self.assumptions: dict[str, Mapping[str, str]] = {}
        self.kb_items: dict[str, ItemDef] = {}
        self.composite: tuple[int, ...] = ()
        self.by_id: dict[str, dict[str, Any]] = {}
        self.modules: dict[str, dict[str, Any]] = {}
        self.diagnosis_groups: Collection[str] | None = None  # aus diagnoses.yaml (T-24 F-02)

    # ---- Ebene KB -----------------------------------------------------------------------------
    def build(self) -> KnowledgeBase:
        self._check_assumptions()
        self._check_composite()
        self._check_items()
        profiles_raw: list[dict[str, Any]] = self.raw["profiles"]
        for index, profile in enumerate(profiles_raw):
            if profile["id"] in self.by_id:
                self.issues.add(f"$.profiles[{index}].id", "duplicate id")
            self.by_id[profile["id"]] = profile
        extended = self._check_extends(profiles_raw)
        regimen_profile = self._check_regimens(profiles_raw, extended)
        blocked = bool(self.issues)
        for profile in profiles_raw:
            self._own_checks(profile)
        diagnosis_modules = self._check_modules(profiles_raw)
        resolved: dict[str, ResolvedProfile] = {}
        compositions: dict[str, ResolvedProfile] = {}
        if not blocked and not self.issues:
            for profile in profiles_raw:
                if profile["id"] in extended:
                    continue
                built = self._resolve(profile)
                if built is None:
                    continue
                target = compositions if profile.get("includes") else resolved
                target[profile["id"]] = built
                for module_id in dict.fromkeys(diagnosis_modules.values()):
                    variant = self._resolve(profile, self.modules[module_id])
                    if variant is not None:
                        compositions[variant.id] = variant
        if self.issues:
            raise TriageError(self.issues.all())
        return KnowledgeBase(
            version=self.raw["version"],
            hash=canonical_hash(self.raw),
            composite_map=self.composite,
            profiles=resolved,
            regimen_profile=regimen_profile,
            assumptions=self.assumptions,
            raw=self.raw,
            compositions=compositions,
            diagnosis_modules=diagnosis_modules,
        )

    def _check_modules(self, profiles: list[dict[str, Any]]) -> dict[str, str]:
        """T-24: Diagnosemodule registrieren, `includes` prüfen (nur Klassenprofile)."""
        mapping: dict[str, str] = {}
        for index, module in enumerate(self.raw.get("modules", [])):
            path = f"$.modules[{index}]"
            if module["id"] in self.modules or module["id"] in self.by_id:
                self.issues.add(f"{path}.id", "duplicate id")
                continue
            self.modules[module["id"]] = module
            self._own_checks(module)
            for group in module["diagnosis_groups"]:
                if self.diagnosis_groups is not None and group not in self.diagnosis_groups:
                    self.issues.add(f"{path}.diagnosis_groups", f"unknown diagnosis group {group}")
                if group in mapping:
                    self.issues.add(f"{path}.diagnosis_groups", "group already has a module")
                mapping[group] = module["id"]
        for profile in profiles:
            for include in profile.get("includes", []):
                path = f"$.profiles[{profile['id']}].includes"
                target = self.by_id.get(include)
                if target is None:
                    self.issues.add(path, f"unknown class profile {include}")
                elif target.get("regimen_ids") or target.get("includes"):
                    self.issues.add(path, f"{include} is not a class profile (module)")
        return mapping

    def _check_assumptions(self) -> None:
        for index, assumption in enumerate(self.raw["assumptions"]):
            if assumption["id"] in self.assumptions:
                self.issues.add(f"$.assumptions[{index}].id", "duplicate id")
            self.assumptions[assumption["id"]] = assumption

    def _provenance(self, raw: Mapping[str, Any], path: str) -> None:
        if not _one_of(raw, path, self.issues):
            return
        reference = raw.get("assumption")
        if reference is not None and reference not in self.assumptions:
            self.issues.add(f"{path}.assumption", "unknown assumption id")

    def _check_composite(self) -> None:
        grading = self.raw["composite_grading"]
        self._provenance(grading, "$.composite_grading")
        values: list[int] = grading["map"]
        # Monotonie des Kerns hängt an einer nicht fallenden Abbildung mit map[0] == 0.
        if values[0] != 0 or any(b < a for a, b in itertools.pairwise(values)):
            self.issues.add("$.composite_grading.map", "must start at 0 and never decrease")
        self.composite = tuple(values)

    def _check_items(self) -> None:
        for index, item in enumerate(self.raw["items"]):
            path = f"$.items[{index}]"
            key = item["symptom_key"]
            if key in self.kb_items:
                self.issues.add(f"{path}.symptom_key", "duplicate id")
                continue
            if key not in self.attributes:
                self.issues.add(f"{path}.symptom_key", "unknown symptom_key (not in items.yaml)")
                continue
            self.kb_items[key] = ItemDef(
                symptom_key=key,
                grade_max=item["grade_max"],
                critical=item["critical"],
                origin=item.get("origin", "custom"),
                burden=float(item.get("burden", 1.0)),
                attributes=tuple(self.attributes[key]),
            )
            presence_only = tuple(self.attributes[key]) == ("presence",)
            if presence_only and item["grade_max"] != 1:
                self.issues.add(f"{path}.grade_max", "presence items must have grade_max 1")

    def _check_extends(self, profiles: list[dict[str, Any]]) -> set[str]:
        extended: set[str] = set()
        for index, profile in enumerate(profiles):
            parent = profile.get("extends")
            if parent is None:
                continue
            if parent not in self.by_id:
                self.issues.add(f"$.profiles[{index}].extends", "unknown profile id")
                continue
            extended.add(parent)
        for profile in profiles:
            seen: list[str] = []
            node: dict[str, Any] | None = profile
            while node is not None:
                if node["id"] in seen:
                    self.issues.add(f"$.profiles[{profile['id']}].extends", "inheritance cycle")
                    break
                seen.append(node["id"])
                node = self.by_id.get(node.get("extends", ""))
        return extended

    def _check_regimens(self, profiles: list[dict[str, Any]], extended: set[str]) -> dict[str, str]:
        mapping: dict[str, str] = {}
        for index, profile in enumerate(profiles):
            for regimen in profile.get("regimen_ids", []):
                path = f"$.profiles[{index}].regimen_ids"
                if regimen not in self.regimens:
                    self.issues.add(path, "unknown regimen id")
                elif profile["id"] in extended:
                    self.issues.add(path, "regimen_ids are only allowed on leaf profiles")
                elif regimen in mapping:
                    self.issues.add(path, "regimen id assigned to more than one profile")
                else:
                    mapping[regimen] = profile["id"]
        for regimen in self.regimens:
            if regimen not in mapping:
                self.issues.add("$.profiles", "regimen without triage profile")
        return mapping

    # ---- Ebene Profil --------------------------------------------------------------------------
    def _own_checks(self, profile: Mapping[str, Any]) -> None:
        """Herkunft und Syntax der im Profil selbst definierten Regeln (auch Zwischenprofile)."""
        base = f"$.profiles[{profile['id']}]"
        teacher = profile.get("teacher", {})
        for kind in ("red", "yellow"):
            for rule in teacher.get(kind, []):
                self._rule_own(rule, f"{base}.teacher.{kind}[{rule['id']}]")
        for floor in profile.get("floors", []):
            self._rule_own(floor, f"{base}.floors[{floor['id']}]")
            if floor.get("locked") is not True:
                self.issues.add(
                    f"{base}.floors[{floor['id']}].locked", "floors must be locked: true"
                )

    def _rule_own(self, rule: Mapping[str, Any], path: str) -> None:
        self._provenance(rule, path)
        try:
            parser.parse(rule["when"])
        except parser.ExpressionError as exc:
            self.issues.add(f"{path}.when", str(exc))

    def _chain(self, leaf: Mapping[str, Any]) -> list[dict[str, Any]]:
        chain: list[dict[str, Any]] = []
        node: dict[str, Any] | None = self.by_id[leaf["id"]]
        while node is not None:
            chain.append(node)
            node = self.by_id.get(node.get("extends", ""))
        chain.reverse()
        return chain

    def _merge(self, chain: list[dict[str, Any]]) -> _Merged:
        merged = _Merged()
        for profile in chain:
            pid = profile["id"]
            base = f"$.profiles[{pid}]"
            loosening = {entry["rule_id"]: entry for entry in profile.get("loosening", [])}
            used: set[str] = set()
            _extend(merged.fixed, profile.get("fixed_items", []))
            _extend(merged.safety, profile.get("safety_items", []))
            screening = profile.get("screening", {})
            if "max_questions" in screening:
                merged.max_questions = screening["max_questions"]
            if "rotating_slots" in screening:
                merged.rotating_slots = screening["rotating_slots"]
            _extend(merged.pool, screening.get("rotation_pool", []))
            merged.priority.update(profile.get("priority", {}))
            for symptom, cascade in profile.get("cascade", {}).items():
                self._merge_cascade(merged, symptom, cascade, f"{base}.cascade.{symptom}")
            for aggregate in profile.get("aggregates", []):
                self._merge_aggregate(merged, aggregate, f"{base}.aggregates[{aggregate['id']}]")
            teacher = profile.get("teacher", {})
            for kind in ("red", "yellow"):
                for rule in teacher.get(kind, []):
                    self._merge_rule(merged, kind, rule, pid, loosening, used, base)
            for floor in profile.get("floors", []):
                self._merge_rule(merged, "floor", floor, pid, loosening, used, base)
            for rule_id in loosening:
                if rule_id not in used:
                    self.issues.add(
                        f"{base}.loosening[{rule_id}]", "loosening does not match a redefined rule"
                    )
        return merged

    def _merge_cascade(
        self, merged: _Merged, symptom: str, cascade: dict[str, Any], path: str
    ) -> None:
        old = merged.cascade.get(symptom)
        if old is None:
            merged.cascade[symptom] = copy.deepcopy(cascade)
            return
        if cascade["attributes_order"] != old["attributes_order"]:
            self.issues.add(
                path, "child may not change the attribute order of an inherited cascade"
            )
        if old.get("escalate_when") is not None and cascade.get("escalate_when") not in (
            None,
            old["escalate_when"],
        ):
            self.issues.add(path, "child may not change an inherited escalate_when (loosening)")
        if cascade.get("escalate_when") is not None and old.get("escalate_when") is None:
            old["escalate_when"] = cascade["escalate_when"]
        _extend(old.setdefault("escalation_items", []), cascade.get("escalation_items", []))

    def _merge_aggregate(self, merged: _Merged, aggregate: dict[str, Any], path: str) -> None:
        old = merged.aggregates.get(aggregate["id"])
        if old is None:
            merged.aggregates[aggregate["id"]] = copy.deepcopy(aggregate)
        elif old != aggregate:
            self.issues.add(path, "aggregate may not be redefined by a child profile")

    def _merge_rule(
        self,
        merged: _Merged,
        kind: str,
        rule: dict[str, Any],
        pid: str,
        loosening: Mapping[str, Any],
        used: set[str],
        base: str,
    ) -> None:
        rule_id = rule["id"]
        path = f"{base}.{kind}[{rule_id}]"
        existing = merged.rules.get(rule_id)
        if existing is None:
            merged.rules[rule_id] = (kind, copy.deepcopy(rule), pid)
            return
        old_kind, old_rule, origin = existing
        if old_kind != kind or origin == pid:
            self.issues.add(path, "duplicate rule id")
            return
        if old_rule["when"] == rule["when"] and old_rule.get("min_level") == rule.get("min_level"):
            return
        if rule_id not in loosening:
            self.issues.add(path, "redefinition loosens an inherited rule without loosening block")
            return
        used.add(rule_id)
        if rule["status"] != "approved":
            self.issues.add(path, "a loosening rule requires status approved")
        merged.rules[rule_id] = (kind, copy.deepcopy(rule), pid)
        merged.loosened.append(rule_id)

    def _universe(self, merged: _Merged) -> list[str]:
        symptoms: list[str] = []
        _extend(symptoms, merged.fixed)
        _extend(symptoms, merged.safety)
        _extend(symptoms, merged.pool)
        index = 0
        while index < len(symptoms):
            cascade = merged.cascade.get(symptoms[index])
            if cascade is not None:
                _extend(symptoms, cascade.get("escalation_items", []))
            index += 1
        return symptoms

    def _modular_chain(
        self, leaf: Mapping[str, Any], module: Mapping[str, Any] | None
    ) -> list[dict[str, Any]]:
        """Vererbungskette plus eingebundene Klassenmodule (je mit eigener Kette, ohne Doppel) und
        optional ein Diagnosemodul; alles über `_merge`, also nur verschärfend (T-24)."""
        chain = self._chain(leaf)
        seen = {p["id"] for p in chain}
        for include in leaf.get("includes", []):
            for node in self._chain(self.by_id[include]):
                if node["id"] not in seen:
                    chain.append(node)
                    seen.add(node["id"])
        if module is not None:
            chain.append(dict(module))
        return chain

    def _resolve(
        self, leaf: Mapping[str, Any], module: Mapping[str, Any] | None = None
    ) -> ResolvedProfile | None:
        chain = self._modular_chain(leaf, module)
        merged = self._merge(chain)
        if module is not None or leaf.get("includes"):
            own = self._merge(self._chain(leaf))  # Blatt ohne Module als Untergrenze (A3 T-24 F-01)
            where = f"$.profiles[{leaf['id']}]" if module is None else f"$.modules[{module['id']}]"
            if (merged.max_questions or 0) < (own.max_questions or 0):
                self.issues.add(
                    f"{where}.screening.max_questions", "module loosens the question limit"
                )
            if merged.rotating_slots < own.rotating_slots:
                self.issues.add(
                    f"{where}.screening.rotating_slots", "module loosens the rotating slots"
                )
            # T-24: wird ein Rotationssymptom durch ein Modul fest gefragt, verlässt es den Pool
            # (häufiger fragen ist strenger); die Slots schrumpfen höchstens auf die Poolgröße.
            asked = {*merged.fixed, *merged.safety}
            merged.pool = [s for s in merged.pool if s not in asked]
            merged.rotating_slots = min(merged.rotating_slots, len(merged.pool))
        pid = leaf["id"] if module is None else f"{leaf['id']}+{module['id']}"
        base = f"$.profiles[{pid}]"
        symptoms = self._universe(merged)
        unknown = [s for s in symptoms if s not in self.kb_items]
        for symptom in unknown:
            self.issues.add(base, f"unknown symptom {symptom} (not an item of the knowledge base)")
        if unknown:
            return None
        module_symptoms: list[str] = []
        if module is not None:  # Diagnosemodul: seine Symptome gehören zum Fragebogen der Gruppe
            for key in ("fixed_items", "safety_items"):
                _extend(module_symptoms, module.get(key, []))
            _extend(module_symptoms, module.get("screening", {}).get("rotation_pool", []))
            for cascade in module.get("cascade", {}).values():
                _extend(module_symptoms, cascade.get("escalation_items", []))
        self._check_screening(merged, leaf, symptoms, base, module_symptoms)
        self._check_critical_are_gates(merged, symptoms, base)
        items = {s: self.kb_items[s] for s in symptoms}
        cascade = self._build_cascades(merged, items, base)
        aggregates = self._build_aggregates(merged, items, base)
        red = yellow = None
        if aggregates is not None:
            red, yellow = self._build_rules(merged, {a.id: a.max_value for a in aggregates}, base)
        floors = self._build_floors(merged, items, base)
        if cascade is None or aggregates is None or red is None or yellow is None or floors is None:
            return None
        status = min((p["status"] for p in chain), key=STATUS_ORDER.index)
        return ResolvedProfile(
            id=pid,
            lineage=tuple(p["id"] for p in chain),
            status=status,
            symptoms=tuple(symptoms),
            fixed_items=tuple(merged.fixed),
            safety_items=tuple(merged.safety),
            rotation_pool=tuple(merged.pool),
            rotating_slots=merged.rotating_slots,
            max_questions=merged.max_questions or 0,
            items=items,
            grade_map=self.composite,
            cascade=cascade,
            aggregates=aggregates,
            red_rules=red,
            yellow_rules=yellow,
            floors=floors,
            priority=dict(merged.priority),
            loosened=tuple(merged.loosened),
            hash=canonical_hash(merged.document([p["id"] for p in chain])),
            regimen_ids=tuple(leaf.get("regimen_ids", [])),
        )

    def _check_critical_are_gates(self, merged: _Merged, symptoms: list[str], base: str) -> None:
        """Kritische Items sind immer Gate-Fragen (fixed/safety), nie nur Eskalationsziel.

        Sonst bliebe ein isoliert schweres kritisches Symptom ungefragt (A3 F-03, triage.md §9).
        """
        always_asked = {*merged.fixed, *merged.safety}
        for symptom in symptoms:
            if self.kb_items[symptom].critical and symptom not in always_asked:
                self.issues.add(
                    base, f"critical item {symptom} must be a fixed or safety item (always asked)"
                )

    def _check_screening(
        self,
        merged: _Merged,
        leaf: Mapping[str, Any],
        symptoms: list[str],
        base: str,
        extra_allowed: Collection[str] = (),
    ) -> None:
        if merged.max_questions is None:
            self.issues.add(f"{base}.screening.max_questions", "required field is missing")
        elif merged.max_questions < len(merged.safety):
            self.issues.add(
                f"{base}.screening.max_questions", "smaller than the number of safety items"
            )
        if merged.rotating_slots > len(merged.pool):
            self.issues.add(
                f"{base}.screening.rotating_slots", "more slots than rotation_pool entries"
            )
        for symptom in merged.pool:
            if symptom in merged.fixed or symptom in merged.safety:
                self.issues.add(
                    f"{base}.screening.rotation_pool", "pool symptom is already a fixed item"
                )
        for regimen in leaf.get("regimen_ids", []):
            allowed = set(self.regimens.get(regimen, ())) | set(extra_allowed)
            if any(s not in allowed for s in symptoms):
                self.issues.add(
                    f"{base}.regimen_ids", f"profile uses symptoms outside regimen {regimen}"
                )

    def _item_domains(
        self, expr: parser.Expr, items: Mapping[str, ItemDef], path: str
    ) -> dict[str, int] | None:
        domains: dict[str, int] = {}
        for name in parser.variables(expr):
            symptom, _, field_name = name.partition(".")
            if field_name not in ("grade", "present") or symptom not in items:
                self.issues.add(
                    path, "name must be <symptom>.grade or <symptom>.present of a profile item"
                )
                return None
            domains[name] = items[symptom].grade_max if field_name == "grade" else 1
        return domains

    def _monotone(self, expr: parser.Expr, domains: Mapping[str, int], path: str) -> None:
        try:
            violation = parser.find_monotone_violation(expr, domains, MAX_GRID_POINTS)
        except parser.ExpressionError as exc:
            self.issues.add(path, str(exc))
            return
        if violation is not None:
            self.issues.add(path, f"not monotone (a higher value lowers the result: {violation})")

    def _build_cascades(
        self, merged: _Merged, items: Mapping[str, ItemDef], base: str
    ) -> dict[str, CascadeDef] | None:
        out: dict[str, CascadeDef] = {}
        failed = False
        for symptom, raw in merged.cascade.items():
            if symptom not in items:
                continue  # Kaskade eines Symptoms außerhalb des Profils: ohne Wirkung
            path = f"{base}.cascade.{symptom}"
            order: list[str] = raw["attributes_order"]
            if len(set(order)) != len(order) or any(
                a not in items[symptom].attributes for a in order
            ):
                self.issues.add(
                    f"{path}.attributes_order", "attributes must be unique and belong to the item"
                )
                failed = True
                continue
            escalation: list[str] = list(raw.get("escalation_items", []))
            text: str | None = raw.get("escalate_when")
            if escalation and text is None:
                self.issues.add(f"{path}.escalate_when", "required when escalation_items are given")
                failed = True
                continue
            expr: parser.Expr | None = None
            if text is not None:
                try:
                    expr = parser.parse(text)
                except parser.ExpressionError as exc:
                    self.issues.add(f"{path}.escalate_when", str(exc))
                    failed = True
                    continue
                domains = self._item_domains(expr, items, f"{path}.escalate_when")
                if domains is None:
                    failed = True
                    continue
                self._monotone(expr, domains, f"{path}.escalate_when")
            out[symptom] = CascadeDef(symptom, tuple(order), text, expr, tuple(escalation))
        return None if failed else out

    def _aggregate_items(
        self, raw: Mapping[str, Any], items: Mapping[str, ItemDef], path: str
    ) -> tuple[str, ...] | None:
        """Ersatzprüfung für `oneOf`: `ALL`, `CRITICAL` oder Liste von Symptomen des Profils."""
        spec = raw.get("items", "ALL" if raw["kind"] == "trend_flag" else None)
        if spec == "ALL":
            return tuple(items)
        if spec == "CRITICAL":
            return tuple(s for s, item in items.items() if item.critical)
        if isinstance(spec, list) and spec and all(isinstance(s, str) for s in spec):
            if all(s in items for s in spec):
                return tuple(spec)
            self.issues.add(f"{path}.items", "aggregate reads a symptom outside the profile")
            return None
        self.issues.add(f"{path}.items", "must be ALL, CRITICAL or a non-empty list of symptoms")
        return None

    def _build_aggregates(
        self, merged: _Merged, items: Mapping[str, ItemDef], base: str
    ) -> tuple[AggregateDef, ...] | None:
        out: list[AggregateDef] = []
        failed = False
        for raw in merged.aggregates.values():
            path = f"{base}.aggregates[{raw['id']}]"
            members = self._aggregate_items(raw, items, path)
            if members is None:
                failed = True
                continue
            kind = raw["kind"]
            threshold = raw.get("threshold")
            if kind == "count_ge" and threshold is None:
                self.issues.add(f"{path}.threshold", "required for count_ge")
                failed = True
                continue
            if kind != "count_ge" and threshold is not None:
                self.issues.add(f"{path}.threshold", "only allowed for count_ge")
                failed = True
                continue
            maxima = [items[s].grade_max for s in members]
            if kind == "max_over":
                domain = max(maxima, default=0)
            elif kind == "min_over":
                domain = min(maxima, default=0)
            elif kind == "count_ge":
                domain = len(members)
            else:
                domain = 1
            out.append(AggregateDef(raw["id"], kind, members, threshold, domain, raw.get("label")))
        return None if failed else tuple(out)

    def _rule_def(
        self, raw: Mapping[str, Any], expr: parser.Expr, level: Level, **extra: Any
    ) -> RuleDef:
        return RuleDef(
            id=raw["id"],
            when=raw["when"],
            expr=expr,
            level=level,
            status=raw["status"],
            source=raw.get("source"),
            assumption=raw.get("assumption"),
            text=raw.get("text"),
            **extra,
        )

    def _build_rules(
        self, merged: _Merged, domains: Mapping[str, int], base: str
    ) -> tuple[tuple[RuleDef, ...] | None, tuple[RuleDef, ...] | None]:
        red: list[RuleDef] = []
        yellow: list[RuleDef] = []
        failed = False
        for rule_id, (kind, raw, _origin) in merged.rules.items():
            if kind == "floor":
                continue
            path = f"{base}.{kind}[{rule_id}].when"
            try:
                expr = parser.parse(raw["when"])
            except parser.ExpressionError as exc:
                self.issues.add(path, str(exc))
                failed = True
                continue
            names = parser.variables(expr)
            unknown = [n for n in names if n not in domains]
            if unknown:
                self.issues.add(
                    path, f"teacher rules may only use aggregates (unknown name {unknown[0]})"
                )
                failed = True
                continue
            if parser.names_under_not(expr):
                self.issues.add(path, "not on an aggregate is forbidden (monotony)")
                failed = True
                continue
            self._monotone(expr, domains, path)
            level = Level.RED if kind == "red" else Level.YELLOW
            definition = self._rule_def(raw, expr, level, loosened=rule_id in merged.loosened)
            (red if kind == "red" else yellow).append(definition)
        return (None if failed else tuple(red)), (None if failed else tuple(yellow))

    def _build_floors(
        self, merged: _Merged, items: Mapping[str, ItemDef], base: str
    ) -> tuple[RuleDef, ...] | None:
        out: list[RuleDef] = []
        failed = False
        for rule_id, (kind, raw, _origin) in merged.rules.items():
            if kind != "floor":
                continue
            path = f"{base}.floors[{rule_id}].when"
            try:
                expr = parser.parse(raw["when"])
            except parser.ExpressionError as exc:
                self.issues.add(path, str(exc))
                failed = True
                continue
            domains = self._item_domains(expr, items, path)
            if domains is None:
                failed = True
                continue
            self._monotone(expr, domains, path)
            symptoms = tuple(dict.fromkeys(name.partition(".")[0] for name in domains))
            out.append(
                self._rule_def(
                    raw,
                    expr,
                    Level[raw["min_level"]],
                    symptoms=symptoms,
                    locked=raw.get("locked") is True,
                    loosened=rule_id in merged.loosened,
                )
            )
        return None if failed else tuple(out)


def build_kb(
    raw: Any,
    *,
    attributes: Mapping[str, Sequence[str]],
    regimens: Mapping[str, Collection[str]],
    diagnosis_groups: Collection[str] | None = None,
) -> KnowledgeBase:
    """Prüft `raw` (bereits geparstes YAML) und baut die Wissensbasis; wirft `TriageError`.

    `attributes`: Symptom → Attribute laut `items.yaml`; `regimens`: Regime-ID → Symptomschlüssel.
    """
    root, definition = _triage_schema()
    found = schema_check.validate(raw, definition, root)
    if found:
        raise TriageError([TriageIssue(i.path, i.message) for i in found])
    builder = _Builder(raw, attributes, regimens)
    builder.diagnosis_groups = diagnosis_groups
    return builder.build()


def read_triage_yaml(directory: Path) -> Any:
    path = directory / TRIAGE_FILE
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise TriageError([TriageIssue("$", "file is missing")]) from None
    except OSError:
        raise TriageError([TriageIssue("$", "file cannot be read")]) from None
    try:
        return yaml.safe_load(text)
    except yaml.MarkedYAMLError as exc:
        line = exc.problem_mark.line + 1 if exc.problem_mark is not None else 0
        raise TriageError([TriageIssue(f"line {line}", "invalid YAML")]) from None
    except yaml.YAMLError:
        raise TriageError([TriageIssue("$", "invalid YAML")]) from None


def load_kb(directory: Path | None = None) -> KnowledgeBase:
    """Lädt `triage.yaml` samt `items.yaml`/`regimens.yaml` aus `directory` (Standard: Inhalt)."""
    base = directory if directory is not None else content_dir()
    content = load_content(base)
    attributes = {
        item["symptom_key"]: [a["attribute"] for a in item["attributes"]]
        for item in content.items["items"]
    }
    regimens = {r["id"]: list(r["symptom_keys"]) for r in content.regimens["regimens"]}
    groups = (
        [g["id"] for g in content.diagnoses["diagnoses"]] if content.diagnoses is not None else None
    )
    return build_kb(
        read_triage_yaml(base), attributes=attributes, regimens=regimens, diagnosis_groups=groups
    )
