"""Inhaltslader: liest `items/regimens/ctcae/rules/report/scenario.yaml` und prüft sie.

Prüfung 1: gegen `challenge/contract/content.schema.json` (eigener Prüfer, `schema_check`).
Prüfung 2: Querverweise (Symptome, CTCAE-Begriffe, Regime, Antwortschlüssel, Eindeutigkeit).
Fehler nennen Datei und Feldpfad, nie Werte. Fehlt der Ordner, ist das kein Fehler (`None`):
Plugin und App laden, der Seed überspringt mit Log.
"""

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

import yaml

from waechter import schema_check
from waechter.constants import CONTENT_DIR_ENV

CHALLENGE_DIR: Final = Path(__file__).resolve().parents[2]
SCHEMA_PATH: Final = CHALLENGE_DIR / "contract" / "content.schema.json"

#: Dateiname → Schema-Definition in `$defs`
FILES: Final = {
    "items": ("items.yaml", "ItemsFile"),
    "regimens": ("regimens.yaml", "RegimensFile"),
    "ctcae": ("ctcae.yaml", "CtcaeFile"),
    "rules": ("rules.yaml", "RulesFile"),
    "report": ("report.yaml", "ReportFile"),
    "scenario": ("scenario.yaml", "ScenarioFile"),
}

#: Dateien ab Vertrag v1.9/v2.1; fehlen sie, ist das kein Fehler (Funktion entfällt, z. B. Fixtures)
OPTIONAL_FILES: Final = {
    "advice": ("advice.yaml", "AdviceFile"),
    "diagnoses": ("diagnoses.yaml", "DiagnosesFile"),
    "schedule": ("schedule.yaml", "ScheduleFile"),
    "medications": ("medications.yaml", "MedicationsFile"),
    "freetext": ("freetext.yaml", "FreeTextFile"),
}
ALL_FILES: Final = {**FILES, **OPTIONAL_FILES}


@dataclass(frozen=True)
class ContentIssue:
    file: str
    path: str
    message: str

    def __str__(self) -> str:
        return f"{self.file}: {self.path}: {self.message}"


class ContentError(ValueError):
    """Mindestens eine Inhaltsdatei fehlt, ist kein YAML oder verletzt Schema/Querverweise."""

    def __init__(self, issues: list[ContentIssue]) -> None:
        self.issues = issues
        super().__init__("; ".join(str(i) for i in issues))


@dataclass(frozen=True)
class Content:
    items: dict[str, Any]
    regimens: dict[str, Any]
    ctcae: dict[str, Any]
    rules: dict[str, Any]
    report: dict[str, Any]
    scenario: dict[str, Any]
    advice: dict[str, Any] | None = None
    diagnoses: dict[str, Any] | None = None
    schedule: dict[str, Any] | None = None
    medications: dict[str, Any] | None = None
    freetext: dict[str, Any] | None = None


class _Loader(yaml.SafeLoader):
    """SafeLoader ohne Zeitstempel-Auflösung: ISO-Zeiten bleiben Zeichenketten (Schema: string)."""


_Loader.yaml_implicit_resolvers = {
    first: [(tag, regexp) for tag, regexp in resolvers if tag != "tag:yaml.org,2002:timestamp"]
    for first, resolvers in yaml.SafeLoader.yaml_implicit_resolvers.items()
}


def content_dir() -> Path:
    """`WAECHTER_CONTENT_DIR` oder `<challenge>/content`."""
    given = os.environ.get(CONTENT_DIR_ENV)
    return Path(given) if given else CHALLENGE_DIR / "content"


def _schema() -> dict[str, Any]:
    loaded: Any = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise ValueError("content.schema.json must be an object")
    return loaded


def _read_yaml(path: Path) -> tuple[Any, list[ContentIssue]]:
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None, [ContentIssue(path.name, "$", "file is missing")]
    except OSError:
        return None, [ContentIssue(path.name, "$", "file cannot be read")]
    try:
        return yaml.load(text, Loader=_Loader), []  # noqa: S506 - eigener SafeLoader
    except yaml.MarkedYAMLError as exc:
        line = exc.problem_mark.line + 1 if exc.problem_mark is not None else 0
        return None, [ContentIssue(path.name, f"line {line}", "invalid YAML")]
    except yaml.YAMLError:
        return None, [ContentIssue(path.name, "$", "invalid YAML")]


def _dicts(node: Any, key: str) -> list[dict[str, Any]]:
    value = node.get(key, []) if isinstance(node, dict) else []
    return [e for e in value if isinstance(e, dict)] if isinstance(value, list) else []


def _cross_check(data: dict[str, dict[str, Any]]) -> list[ContentIssue]:
    out: list[ContentIssue] = []
    items_file, regimens_file = FILES["items"][0], FILES["regimens"][0]
    scenario_file, rules_file = FILES["scenario"][0], FILES["rules"][0]

    symptoms: set[str] = set()
    pairs: set[str] = set()
    for i, item in enumerate(data["items"]["items"]):
        key = item["symptom_key"]
        if key in symptoms:
            out.append(ContentIssue(items_file, f"$.items[{i}].symptom_key", "duplicate id"))
        symptoms.add(key)
        pairs.update(f"{key}.{a['attribute']}" for a in item["attributes"])
    ctcae_ids = {t["id"] for t in data["ctcae"]["terms"]}
    for i, item in enumerate(data["items"]["items"]):
        for j, term in enumerate(item["ctcae_terms"]):
            if term not in ctcae_ids:
                out.append(
                    ContentIssue(items_file, f"$.items[{i}].ctcae_terms[{j}]", "unknown CTCAE id")
                )

    regimen_ids: set[str] = set()
    for i, regimen in enumerate(data["regimens"]["regimens"]):
        if regimen["id"] in regimen_ids:
            out.append(ContentIssue(regimens_file, f"$.regimens[{i}].id", "duplicate id"))
        regimen_ids.add(regimen["id"])
        for j, key in enumerate(regimen["symptom_keys"]):
            if key not in symptoms:
                out.append(
                    ContentIssue(
                        regimens_file, f"$.regimens[{i}].symptom_keys[{j}]", "unknown symptom_key"
                    )
                )
        for j, note in enumerate(regimen.get("watch_notes", [])):
            if note["symptom_key"] not in symptoms:
                out.append(
                    ContentIssue(
                        regimens_file,
                        f"$.regimens[{i}].watch_notes[{j}].symptom_key",
                        "unknown symptom_key",
                    )
                )

    for i, rule in enumerate(data["rules"]["rules"]):
        for j, key in enumerate(rule.get("symptom_keys", [])):
            if key not in symptoms:
                out.append(
                    ContentIssue(
                        rules_file, f"$.rules[{i}].symptom_keys[{j}]", "unknown symptom_key"
                    )
                )

    pseudonyms: set[str] = set()
    usernames: set[str] = set()
    for i, patient in enumerate(data["scenario"]["patients"]):
        base = f"$.patients[{i}]"
        if patient["pseudonym"] in pseudonyms:
            out.append(ContentIssue(scenario_file, f"{base}.pseudonym", "duplicate id"))
        pseudonyms.add(patient["pseudonym"])
        username = patient.get("username")
        if username is not None:
            if username in usernames:
                out.append(ContentIssue(scenario_file, f"{base}.username", "duplicate id"))
            usernames.add(username)
        if patient["regimen_id"] not in regimen_ids:
            out.append(ContentIssue(scenario_file, f"{base}.regimen_id", "unknown regimen id"))
        for j, response in enumerate(patient["responses"]):
            out.extend(
                ContentIssue(scenario_file, f"{base}.responses[{j}].answers.{key}", "unknown item")
                for key in response["answers"]
                if key not in pairs
            )
    return out


def _cross_check_medications(data: dict[str, dict[str, Any]]) -> list[ContentIssue]:
    """regimen_ids ⊆ regimens.yaml, spc_source_id ∈ Quellen der Regime, eindeutige IDs und Codes."""
    medications = data.get("medications")
    if medications is None:
        return []
    out: list[ContentIssue] = []
    name = OPTIONAL_FILES["medications"][0]
    regimens = {r["id"] for r in data["regimens"]["regimens"]}
    sources = {s["id"] for r in data["regimens"]["regimens"] for s in r.get("sources", [])}
    ids: set[str] = set()
    codes: set[str] = set()
    for i, med in enumerate(medications["medications"]):
        base = f"$.medications[{i}]"
        if med["id"] in ids:
            out.append(ContentIssue(name, f"{base}.id", "duplicate id"))
        ids.add(med["id"])
        code = med.get("sukl_code")
        if code is not None:
            if code in codes:
                out.append(ContentIssue(name, f"{base}.sukl_code", "duplicate code"))
            codes.add(code)
        out.extend(
            ContentIssue(name, f"{base}.regimen_ids[{j}]", "unknown regimen id")
            for j, regimen in enumerate(med["regimen_ids"])
            if regimen not in regimens
        )
        source = med.get("spc_source_id")
        if source is not None and source not in sources:
            out.append(ContentIssue(name, f"{base}.spc_source_id", "unknown source id"))
    return out


def _cross_check_freetext(
    data: dict[str, dict[str, Any]], symptoms: set[str]
) -> list[ContentIssue]:
    """symptom_key ∈ items.yaml, je Symptom höchstens ein Eintrag, eindeutige Warnwort-IDs."""
    freetext = data.get("freetext")
    if freetext is None:
        return []
    name = OPTIONAL_FILES["freetext"][0]
    out: list[ContentIssue] = []
    seen: set[str] = set()
    for i, entry in enumerate(freetext["synonyms"]):
        base = f"$.synonyms[{i}]"
        if entry["symptom_key"] not in symptoms:
            out.append(ContentIssue(name, f"{base}.symptom_key", "unknown symptom_key"))
        if entry["symptom_key"] in seen:
            out.append(ContentIssue(name, f"{base}.symptom_key", "duplicate symptom_key"))
        seen.add(entry["symptom_key"])
    ids: set[str] = set()
    for i, word in enumerate(freetext.get("warn_words", [])):
        if word["id"] in ids:
            out.append(ContentIssue(name, f"$.warn_words[{i}].id", "duplicate id"))
        ids.add(word["id"])
    lists = [(f"$.synonyms[{i}].terms", e["terms"]) for i, e in enumerate(freetext["synonyms"])] + [
        (f"$.warn_words[{i}].terms", w["terms"])
        for i, w in enumerate(freetext.get("warn_words", []))
    ]
    for path, terms in lists:
        for language, words in terms.items():
            out.extend(
                ContentIssue(name, f"{path}.{language}[{j}]", "term longer than 40 characters")
                for j, word in enumerate(words)
                if len(word) > 40
            )
    return out


def _cross_check_clinic(data: dict[str, dict[str, Any]]) -> list[ContentIssue]:
    """Querverweise der v1.9/v2.1-Dateien (advice, diagnoses, schedule), soweit vorhanden."""
    out: list[ContentIssue] = []
    symptoms = {i["symptom_key"] for i in data["items"]["items"]}
    advice = data.get("advice")
    if advice is not None:
        name = OPTIONAL_FILES["advice"][0]
        source_ids = {s["id"] for s in advice.get("sources", [])}
        rule_ids: set[str] = set()
        for i, key in enumerate(advice["escalation"].get("always_acute_for", [])):
            if key not in symptoms:
                out.append(
                    ContentIssue(name, f"$.escalation.always_acute_for[{i}]", "unknown symptom_key")
                )
        for i, rule in enumerate(advice["advice"]):
            base = f"$.advice[{i}]"
            if rule["id"] in rule_ids:
                out.append(ContentIssue(name, f"{base}.id", "duplicate id"))
            rule_ids.add(rule["id"])
            if rule["symptom_key"] not in symptoms:
                out.append(ContentIssue(name, f"{base}.symptom_key", "unknown symptom_key"))
            if rule.get("max_value", 4) < rule["min_value"]:
                out.append(ContentIssue(name, f"{base}.max_value", "below min_value"))
            out.extend(
                ContentIssue(name, f"{base}.source_ids[{j}]", "unknown source id")
                for j, source in enumerate(rule["source_ids"])
                if source not in source_ids
            )
    diagnoses = data.get("diagnoses")
    if diagnoses is not None:
        name = OPTIONAL_FILES["diagnoses"][0]
        ids: set[str] = set()
        prefixes: set[str] = set()
        for i, group in enumerate(diagnoses["diagnoses"]):
            base = f"$.diagnoses[{i}]"
            if group["id"] in ids:
                out.append(ContentIssue(name, f"{base}.id", "duplicate id"))
            ids.add(group["id"])
            for j, prefix in enumerate(group["icd10_prefixes"]):
                if prefix in prefixes:
                    out.append(
                        ContentIssue(name, f"{base}.icd10_prefixes[{j}]", "duplicate prefix")
                    )
                prefixes.add(prefix)
            out.extend(
                ContentIssue(name, f"{base}.symptom_keys[{j}]", "unknown symptom_key")
                for j, key in enumerate(group["symptom_keys"])
                if key not in symptoms
            )
    out.extend(_cross_check_medications(data))
    out.extend(_cross_check_freetext(data, symptoms))
    schedule = data.get("schedule")
    if schedule is not None:
        name = OPTIONAL_FILES["schedule"][0]
        out.extend(
            ContentIssue(name, f"$.phases[{i}].to_cycle_day", "below from_cycle_day")
            for i, phase in enumerate(schedule["phases"])
            if phase["to_cycle_day"] < phase["from_cycle_day"]
        )
    return out


def validate_document(kind: str, document: Any) -> list[ContentIssue]:
    """Prüft ein einzelnes Dokument (`rules` oder `report`) gegen das Schema der Datei.

    Grundlage für Änderungen über die API: dieselben Regeln wie beim Laden der Dateien, Fehler mit
    Feldpfad und ohne Werte.
    """
    filename, definition = FILES[kind]
    schema = _schema()
    found = schema_check.validate(document, schema["$defs"][definition], schema)
    return [ContentIssue(filename, i.path, i.message) for i in found]


def load_content(directory: Path) -> Content:
    """Lädt und prüft alle Dateien; wirft `ContentError` mit allen gefundenen Verstößen."""
    schema = _schema()
    defs: dict[str, Any] = schema["$defs"]
    data: dict[str, Any] = {}
    issues: list[ContentIssue] = []
    for name, (filename, definition) in ALL_FILES.items():
        if name in OPTIONAL_FILES and not (directory / filename).is_file():
            continue
        raw, read_issues = _read_yaml(directory / filename)
        issues.extend(read_issues)
        if read_issues:
            continue
        found = schema_check.validate(raw, defs[definition], schema)
        issues.extend(ContentIssue(filename, i.path, i.message) for i in found)
        data[name] = raw
    if not issues:
        issues = [*_cross_check(data), *_cross_check_clinic(data)]
    if issues:
        raise ContentError(issues)
    return Content(**data)


_cache: dict[Path, tuple[tuple[tuple[str, int, int], ...], Content]] = {}


def _fingerprint(directory: Path) -> tuple[tuple[str, int, int], ...]:
    stamps: list[tuple[str, int, int]] = []
    for filename, _ in ALL_FILES.values():
        try:
            stat = (directory / filename).stat()
        except OSError:
            stamps.append((filename, -1, -1))
        else:
            stamps.append((filename, stat.st_mtime_ns, stat.st_size))
    return tuple(stamps)


def get_content() -> Content | None:
    """Geprüfter Inhalt des aktuellen Inhaltsordners; `None`, wenn der Ordner fehlt.

    Ergebnis wird je Ordner zwischengespeichert und bei geänderten Dateien neu geladen.
    """
    directory = content_dir()
    if not directory.is_dir():
        return None
    key = directory.resolve()
    fingerprint = _fingerprint(directory)
    cached = _cache.get(key)
    if cached is not None and cached[0] == fingerprint:
        return cached[1]
    content = load_content(directory)
    _cache[key] = (fingerprint, content)
    return content
