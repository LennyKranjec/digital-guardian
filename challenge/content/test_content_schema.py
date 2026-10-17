"""Inhaltsdateien (T-01, Owner A1): jede YAML gegen ihre $defs-Definition in challenge/contract/content.schema.json.

`jsonschema` ist nicht installiert (keine neue Abhängigkeit ohne A0-Entscheid) ⇒ kleiner eigener Validator für genau die im
Schema verwendeten Schlüsselwörter. Unbekannte Schlüsselwörter lassen den Test fehlschlagen (kein stilles Durchwinken).
Zusätzlich: Querverweise zwischen den Dateien, cs/en-Vollständigkeit, Verbotsliste für Patiententexte, Orakel gegen `expected`.
"""

from __future__ import annotations

import importlib.util
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest
import yaml

CONTENT = Path(__file__).resolve().parent
SCHEMA_PATH = CONTENT.parent / "contract" / "content.schema.json"
FILES = {
    "items.yaml": "ItemsFile",
    "regimens.yaml": "RegimensFile",
    "ctcae.yaml": "CtcaeFile",
    "rules.yaml": "RulesFile",
    "report.yaml": "ReportFile",
    "scenario.yaml": "ScenarioFile",
    "advice.yaml": "AdviceFile",  # T-12 / Vertrag v1.9
    "diagnoses.yaml": "DiagnosesFile",
    "schedule.yaml": "ScheduleFile",
    "freetext.yaml": "FreeTextFile",  # T-22 / T-22a
}
IGNORED_KEYWORDS = {"$schema", "$id", "title", "description", "default", "$defs"}
KNOWN_KEYWORDS = IGNORED_KEYWORDS | {
    "$ref", "type", "required", "properties", "additionalProperties", "items", "minItems", "maxItems", "minLength",
    "minimum", "maximum", "pattern", "enum", "const", "propertyNames", "format", "maxLength",
}  # fmt: skip


# --------------------------------------------------------------------------------------------------------------------
# Minimal-Validator
# --------------------------------------------------------------------------------------------------------------------
def _type_ok(value: Any, name: str) -> bool:
    if name == "string":
        return isinstance(value, str)
    if name == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if name == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if name == "boolean":
        return isinstance(value, bool)
    if name == "object":
        return isinstance(value, dict)
    if name == "array":
        return isinstance(value, list)
    if name == "null":
        return value is None
    raise AssertionError(f"unbekannter Typ im Schema: {name}")


def validate(value: Any, schema: dict, root: dict, path: str = "$") -> list[str]:
    errors: list[str] = []
    unknown = set(schema) - KNOWN_KEYWORDS
    assert not unknown, f"{path}: Validator kennt Schlüsselwörter nicht: {unknown}"
    if "$ref" in schema:
        ref = schema["$ref"]
        assert ref.startswith("#/$defs/"), f"nur lokale $ref unterstützt: {ref}"
        errors += validate(value, root["$defs"][ref.removeprefix("#/$defs/")], root, path)
    if "const" in schema and value != schema["const"]:
        errors.append(f"{path}: erwartet {schema['const']!r}, ist {value!r}")
    if "enum" in schema and value not in schema["enum"]:
        errors.append(f"{path}: {value!r} nicht in {schema['enum']}")
    if "type" in schema:
        types = schema["type"] if isinstance(schema["type"], list) else [schema["type"]]
        if not any(_type_ok(value, t) for t in types):
            errors.append(f"{path}: Typ {type(value).__name__} nicht in {types}")
            return errors
    if isinstance(value, str):
        if "minLength" in schema and len(value) < schema["minLength"]:
            errors.append(f"{path}: kürzer als {schema['minLength']}")
        if "maxLength" in schema and len(value) > schema["maxLength"]:
            errors.append(f"{path}: länger als {schema['maxLength']}")
        if "pattern" in schema and not re.search(schema["pattern"], value):
            errors.append(f"{path}: {value!r} passt nicht auf {schema['pattern']}")
        if schema.get("format") == "date-time":
            try:
                datetime.fromisoformat(value)
            except ValueError:
                errors.append(f"{path}: kein ISO-8601-Zeitpunkt: {value!r}")
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            errors.append(f"{path}: {value} < {schema['minimum']}")
        if "maximum" in schema and value > schema["maximum"]:
            errors.append(f"{path}: {value} > {schema['maximum']}")
    if isinstance(value, list):
        if "minItems" in schema and len(value) < schema["minItems"]:
            errors.append(f"{path}: weniger als {schema['minItems']} Elemente")
        if "maxItems" in schema and len(value) > schema["maxItems"]:
            errors.append(f"{path}: mehr als {schema['maxItems']} Elemente")
        if "items" in schema:
            for i, item in enumerate(value):
                errors += validate(item, schema["items"], root, f"{path}[{i}]")
    if isinstance(value, dict):
        for name in schema.get("required", []):
            if name not in value:
                errors.append(f"{path}: Pflichtfeld {name!r} fehlt")
        props = schema.get("properties", {})
        extra = schema.get("additionalProperties", True)
        for key, sub in value.items():
            if "propertyNames" in schema:
                errors += validate(
                    key, schema["propertyNames"], root, f"{path}.<Schlüssel {key!r}>"
                )
            if key in props:
                errors += validate(sub, props[key], root, f"{path}.{key}")
            elif extra is False:
                errors.append(f"{path}: unerwartetes Feld {key!r}")
            elif isinstance(extra, dict):
                errors += validate(sub, extra, root, f"{path}.{key}")
    return errors


# --------------------------------------------------------------------------------------------------------------------
# Fixtures
# --------------------------------------------------------------------------------------------------------------------
@pytest.fixture(scope="module")
def schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def data() -> dict[str, Any]:
    return {name: yaml.safe_load((CONTENT / name).read_text(encoding="utf-8")) for name in FILES}


def _oracle_module() -> Any:
    spec = importlib.util.spec_from_file_location(
        "waechter_content_oracle", CONTENT / "tools" / "oracle.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # dataclasses (Python 3.14) schlägt Typen über sys.modules nach
    spec.loader.exec_module(module)
    return module


# --------------------------------------------------------------------------------------------------------------------
# Schema
# --------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("filename", sorted(FILES))
def test_file_matches_schema_definition(filename: str, schema: dict, data: dict[str, Any]) -> None:
    errors = validate(data[filename], {"$ref": f"#/$defs/{FILES[filename]}"}, schema)
    assert not errors, f"{filename}:\n" + "\n".join(errors)


def test_validator_detects_violations(schema: dict) -> None:
    """Der Eigenbau-Validator darf nicht alles durchwinken (Gegenprobe)."""
    bad_rules = {
        "version": "rules-1",
        "rules": [
            {"id": "x", "kind": "magic", "level": "blue", "enabled": "ja", "params": {"a": "b"}}
        ],
        "noise": {},
    }
    errors = validate(bad_rules, {"$ref": "#/$defs/RulesFile"}, schema)
    assert len(errors) >= 8, errors
    bad_text = {"cs": "nur tschechisch"}
    assert validate(bad_text, {"$ref": "#/$defs/LocalizedText"}, schema) == [
        "$: Pflichtfeld 'en' fehlt"
    ]
    assert validate({"cs": "a", "en": ""}, {"$ref": "#/$defs/LocalizedText"}, schema)


# --------------------------------------------------------------------------------------------------------------------
# Querverweise
# --------------------------------------------------------------------------------------------------------------------
def test_items_scales_and_ctcae_links(data: dict[str, Any]) -> None:
    items = data["items.yaml"]
    ctcae_ids = {t["id"] for t in data["ctcae.yaml"]["terms"]}
    keys = [i["symptom_key"] for i in items["items"]]
    assert len(keys) == len(set(keys))
    assert 10 <= len(keys) <= 14
    core = {i["symptom_key"] for i in items["items"] if i.get("core")}
    assert {"fatigue", "nausea", "diarrhea", "fever", "pain"} <= core
    for it in items["items"]:
        assert 1 <= len(it["attributes"]) <= 3
        attrs = [a["attribute"] for a in it["attributes"]]
        assert len(attrs) == len(set(attrs))
        for a in attrs:
            assert a in items["scale_labels"], f"{it['symptom_key']}.{a}: keine Skalenbeschriftung"
        assert it["ctcae_terms"], it["symptom_key"]
        assert set(it["ctcae_terms"]) <= ctcae_ids, it["symptom_key"]
    for attr, labels in items["scale_labels"].items():
        assert len(labels) == (2 if attr == "presence" else 5), attr
    assert (
        next(i for i in items["items"] if i["symptom_key"] == "fever")["attributes"][0]["attribute"]
        == "presence"
    )
    used_terms = {t for i in items["items"] for t in i["ctcae_terms"]}
    assert used_terms == ctcae_ids, (
        "ctcae.yaml enthält Begriffe, die kein Item nutzt (oder umgekehrt)"
    )


def test_ctcae_terms_have_source_and_grades(data: dict[str, Any]) -> None:
    ctcae = data["ctcae.yaml"]
    assert ctcae["source"]["id"] == "SRC-CTCAE-V6"
    codes = [t["meddra_code"] for t in ctcae["terms"]]
    assert len(codes) == len(set(codes))
    for t in ctcae["terms"]:
        assert t.get("locator", "").startswith("PDF S."), t["id"]
        assert t["grades"], t["id"]
        assert t["label"]["cs"] and t["label"]["en"]
        # Wortlaut-Stichprobe aus der Einleitung des PDFs (S. 2): Grad 5 = Tod, wenn definiert
        if "5" in t["grades"]:
            assert t["grades"]["5"] == "Death", t["id"]


def test_regimens_reference_items_and_sources(data: dict[str, Any]) -> None:
    items = {i["symptom_key"] for i in data["items.yaml"]["items"]}
    regimens = data["regimens.yaml"]["regimens"]
    assert len(regimens) == 8  # T-20: + ENZALUTAMIDE, ABIRATERONE, PAZOPANIB, NIVOLUMAB
    assert len({r["id"] for r in regimens}) == 8
    covered: set[str] = set()
    for r in regimens:
        assert set(r["symptom_keys"]) <= items, r["id"]
        covered |= set(r["symptom_keys"])
        source_ids = {s["id"] for s in r["sources"]}
        assert source_ids and all(
            s["claim_level"] == "B" and s.get("locator") and s.get("url") for s in r["sources"]
        )
        assert r["watch_notes"], r["id"]
        for n in r["watch_notes"]:
            assert n["symptom_key"] in r["symptom_keys"], (r["id"], n["symptom_key"])
            assert n["source_id"] in source_ids, (r["id"], n["source_id"])
    core = {i["symptom_key"] for i in data["items.yaml"]["items"] if i.get("core")}
    assert items - core <= covered, "Profil-Items ohne Regime: " + str(items - core - covered)


def test_rules_match_ticket_and_contract(data: dict[str, Any]) -> None:
    rules = data["rules.yaml"]
    assert rules["version"] == "rules-v1"
    by_id = {r["id"]: r for r in rules["rules"]}
    assert set(by_id) == {"R-SEV-01", "R-URG-01", "R-DLT-01", "R-TRD-01", "R-MIS-01"}
    assert (by_id["R-SEV-01"]["kind"], by_id["R-SEV-01"]["level"], by_id["R-SEV-01"]["params"]) == (
        "threshold",
        "red",
        {"min_value": 3},
    )
    assert set(by_id["R-SEV-01"]["attributes"]) == {"severity", "interference"}
    assert by_id["R-URG-01"]["symptom_keys"] == ["fever"] and by_id["R-URG-01"]["attributes"] == [
        "presence"
    ]
    assert (by_id["R-URG-01"]["level"], by_id["R-URG-01"]["params"]) == ("red", {"min_value": 1})
    assert (by_id["R-DLT-01"]["kind"], by_id["R-DLT-01"]["level"]) == ("baseline_delta", "yellow")
    assert by_id["R-DLT-01"]["params"] == {"baseline_days": 7, "min_delta": 2, "min_value": 2}
    assert (by_id["R-TRD-01"]["kind"], by_id["R-TRD-01"]["level"]) == ("trend", "yellow")
    assert by_id["R-TRD-01"]["params"] == {
        "window_days": 10,
        "min_points": 4,
        "horizon_days": 5,
        "target_value": 3,
        "min_slope_per_day": 0.15,
    }
    assert (by_id["R-MIS-01"]["kind"], by_id["R-MIS-01"]["level"], by_id["R-MIS-01"]["params"]) == (
        "missing",
        "grey",
        {"max_days_without_response": 3},
    )
    assert rules["noise"] == {
        "notify_levels": ["red"],
        "digest_levels": ["yellow", "grey"],
        "cooldown_hours": 24,
    }
    item_keys = {i["symptom_key"] for i in data["items.yaml"]["items"]}
    for r in rules["rules"]:
        assert set(r.get("symptom_keys", [])) <= item_keys, r["id"]
        # jede Regel trägt ehrlich "nicht validiert" bzw. eine Quelle
        text = (r["rationale"]["en"] + r["rationale"]["cs"]).lower()
        assert "not clinically validated" in r["rationale"]["en"] or r.get("source_id"), r["id"]
        assert "klinicky neověřeno" in text or r.get("source_id"), r["id"]
        if r.get("source_id"):
            assert r["source_id"] == data["ctcae.yaml"]["source"]["id"]


def test_report_has_all_sections(data: dict[str, Any]) -> None:
    report = data["report.yaml"]
    assert report["since"] == "last_visit"
    assert report["sections"] == [
        "summary",
        "alerts",
        "timeline",
        "since_last_visit",
        "therapy",
        "assessments",
        "missing_data",
        "audit",
    ]


# --------------------------------------------------------------------------------------------------------------------
# Szenario und Orakel
# --------------------------------------------------------------------------------------------------------------------
def test_scenario_is_synthetic_and_consistent(data: dict[str, Any]) -> None:
    sc = data["scenario.yaml"]
    assert sc["synthetic"] is True
    assert str(sc["anchor"]) == "2026-10-17T09:00:00+02:00"
    pats = sc["patients"]
    assert [p["pseudonym"] for p in pats] == [
        f"SYN-000{i}" for i in range(1, 8)
    ]  # T-20: + SYN-0006, SYN-0007
    assert len({p["display_name"] for p in pats}) == 7
    regimens = {r["id"]: r for r in data["regimens.yaml"]["regimens"]}
    items = data["items.yaml"]["items"]
    main = pats[0]
    assert main["username"] == "patient" and main["regimen_id"] == "FOLFOX"
    assert [v for v in main["visits"] if v["kind"] == "past"][-1]["day_offset"] == -14
    assert [v["day_offset"] for v in main["visits"] if v["kind"] == "planned"] == [1]
    assert pats[1]["username"] == "patient2"  # Vertrag v1.1 G-14
    assert sum(1 for p in pats if p.get("username")) == 2
    for p in pats:
        core = {i["symptom_key"] for i in items if i.get("core")}
        profile = set(regimens[p["regimen_id"]]["symptom_keys"])
        allowed = {
            f"{i['symptom_key']}.{a['attribute']}"
            for i in items
            if i["symptom_key"] in core | profile
            for a in i["attributes"]
        }
        offsets = [r["day_offset"] for r in p["responses"]]
        assert offsets == sorted(offsets) and len(offsets) == len(set(offsets)), p["pseudonym"]
        assert min(offsets) >= -21 and max(offsets) <= 0
        for r in p["responses"]:
            assert set(r["answers"]) == allowed, (p["pseudonym"], r["day_offset"])
        assert not re.search(r"[@]|\b\d{9,}\b", yaml.safe_dump(p)), (
            "Verdacht auf echte Personendaten"
        )
    # Hauptdemo: 2 fehlende Tage als Lücke, einzelne übersprungene Antworten
    offs = [r["day_offset"] for r in main["responses"]]
    assert -13 not in offs and -12 not in offs and offs[-1] == -1
    assert any(v is None for r in main["responses"] for v in r["answers"].values())
    # SYN-0004: letzte Antwort Tag -5
    assert max(r["day_offset"] for r in pats[3]["responses"]) == -5


def test_oracle_reproduces_expected_and_is_interpretation_robust(data: dict[str, Any]) -> None:
    oracle = _oracle_module()
    rules, scenario = oracle.load()
    sc = data["scenario.yaml"]
    expected_lights = {
        "SYN-0001": "red",
        "SYN-0002": "green",
        "SYN-0003": "yellow",
        "SYN-0004": "grey",
        "SYN-0005": "red",
        "SYN-0006": "red",
        "SYN-0007": "yellow",
    }
    # von Hand festgelegt (SOURCES.md §5), unabhängig vom Orakelcode: (Regel, Symptom, Attribut, Stufe, Tag, Stunde)
    expected_alerts = {
        "SYN-0001": {
            ("R-TRD-01", "peripheral_neuropathy", "severity", "yellow", -5, 19),
            ("R-SEV-01", "diarrhea", "severity", "red", -1, 19),
        },
        "SYN-0002": set(),
        "SYN-0003": {("R-DLT-01", "hand_foot", "severity", "yellow", -2, 20)},
        "SYN-0004": set(),
        "SYN-0005": {("R-URG-01", "fever", "presence", "red", 0, 7)},
        # T-20 (SOURCES.md §9, mit eigenem Bruchrechnungsskript nachgerechnet)
        "SYN-0006": {
            ("R-TRD-01", "fatigue", "severity", "yellow", -13, 19),
            ("R-URG-01", "fever", "presence", "red", 0, 7),
        },
        "SYN-0007": {
            ("R-DLT-01", "diarrhea", "severity", "yellow", -3, 19),
            ("R-DLT-01", "hand_foot", "severity", "yellow", -1, 19),
        },
    }
    for p in sc["patients"]:
        result = oracle.oracle(rules, scenario, p)  # wirft bei Auslegungsabhängigkeit
        assert oracle.expected_block(result) == p["expected"], p["pseudonym"]
        assert p["expected"]["traffic_light_at_anchor"] == expected_lights[p["pseudonym"]]
        got = {
            (a["rule_id"], a["symptom_key"], a["attribute"], a["level"], a["day_offset"], a["hour"])
            for a in p["expected"]["alerts"]
        }
        assert got == expected_alerts[p["pseudonym"]], p["pseudonym"]
        assert all(
            a["rule_id"] != "R-MIS-01" for a in p["expected"]["alerts"]
        )  # R-MIS-01 nur in der Ampel


# --------------------------------------------------------------------------------------------------------------------
# Verbotsliste für Patiententexte (Items): keine Diagnose, Beruhigung, Alarm, Reaktionszusage
# --------------------------------------------------------------------------------------------------------------------
FORBIDDEN = [
    r"diagnos", r"diagnóz", r"\bdiagnose\b", r"nebezpe", r"danger", r"alarm", r"emergency", r"urgent", r"immediately", r"okamžit",
    r"no need to worry", r"don'?t worry", r"keine sorge", r"nemějte obav", r"nic se neděje", r"nothing to worry", r"everything is (fine|ok)",
    r"will contact you", r"vás kontaktuje", r"we will call", r"call (your|the) doctor", r"zavolejte", r"\b112\b", r"\b155\b",
    r"seek (medical )?(help|care)", r"vyhledejte", r"you (suffer|are suffering)", r"trpíte",
]  # fmt: skip


def _patient_texts(items_file: dict) -> list[str]:
    texts = [items_file["recall_period"]["cs"], items_file["recall_period"]["en"]]
    for labels in items_file["scale_labels"].values():
        texts += [t for lab in labels for t in lab.values()]
    for it in items_file["items"]:
        texts += list(it["label"].values())
        for a in it["attributes"]:
            texts += list(a["question"].values())
    return texts


def test_patient_texts_contain_no_forbidden_statements(data: dict[str, Any]) -> None:
    texts = _patient_texts(data["items.yaml"])
    assert len(texts) > 60
    for text in texts:
        for pattern in FORBIDDEN:
            assert not re.search(pattern, text, re.IGNORECASE), f"{pattern!r} in {text!r}"


def test_every_localized_text_has_cs_and_en(data: dict[str, Any]) -> None:
    def walk(node: Any, where: str) -> None:
        if isinstance(node, dict):
            if "cs" in node or "en" in node:
                assert node.get("cs", "").strip() and node.get("en", "").strip(), where
            for k, v in node.items():
                walk(v, f"{where}.{k}")
        elif isinstance(node, list):
            for i, v in enumerate(node):
                walk(v, f"{where}[{i}]")

    for name in (
        "items.yaml", "regimens.yaml", "ctcae.yaml", "rules.yaml", "advice.yaml", "diagnoses.yaml", "schedule.yaml"
    ):  # fmt: skip
        walk(data[name], name)


# --------------------------------------------------------------------------------------------------------------------
# T-12 / Vertrag v1.9 (DR-020): Rady pacientovi, Diagnose-Anpassung, Intervalle, SÚKL-SPC-Quellen
# --------------------------------------------------------------------------------------------------------------------
#: Verbotsliste des Frontends (challenge/frontend/waechter/i18n/forbidden.ts, Stand int/3) als Kopie – das Frontend liegt auf
#: main noch nicht vor; `test_frontend_forbidden_list_is_not_stale` gleicht gegen die echte Datei ab, sobald sie da ist.
FORBIDDEN_FE = [
    "keine sorge", "keine sorgen", "harmlos", "alles in ordnung", "unbedenklich", "keine gefahr", "nebojte", "v pořádku",
    "neškodn", "nic se neděje", "žádný důvod k obavám", "don't worry", "do not worry", "harmless", "you are fine",
    "you're fine", "nothing to worry", "all clear", "no cause for concern", "diagnose", "diagnos", "diagnóz", "alarm",
    "notfall", "lebensgefahr", "ampel", "semafor", "traffic light", "wir melden uns", "wir kümmern uns", "wird sich melden",
    "ozveme se", "we will contact you", "we'll contact you", "we will call you", "someone will call",
]  # fmt: skip
#: Regex des A3-Tests (challenge/backend/test_a3_realcontent.py::FORBIDDEN), Kopie
FORBIDDEN_A3 = re.compile(
    r"ampel|semafor|traffic|alarm|\balert|červen|žlut|\bred\b|yellow|\bgrade\b|stupeň|ctcae"
    r"|diagnos|doporuč|recommend|empfehl|keine sorge|don.?t worry|no need to worry"
    r"|nemusíte se bát|v pořádku|alles in ordnung|all is (fine|well)|we will (contact|call)"
    r"|ozveme se|zavoláme|wir (melden|rufen)|notfall|emergency|nouz",
    re.IGNORECASE,
)
#: Reaktionszusage, Medikamente/Dosierungen, Therapieänderung – in Tipps und Eskalation verboten (DR-020)
FORBIDDEN_ADVICE_EXTRA = re.compile(
    r"tým (byl|bude|se )|team (was|will|has been)|will be (informed|contacted|notified)|informován|bude(te)? kontaktován"
    r"|\bmg\b|\bml\b|tablet|dávk|\bdose|dosage|\bpills?\b|ibuprofen|paracetamol|acetaminophen|aspirin|loperamid|imodium"
    r"|antibiotik|kortikoid|steroid|opioid|morfin|\blék|medicin|medikac|prescri|předeps"
    r"|přestaňte|vysaďte|stop taking|stop your|změňte dávk|change your dose",
    re.IGNORECASE,
)


def _all_advice_texts(advice: dict) -> list[tuple[str, str]]:
    """(Ort, Text) aller Patiententexte aus advice.yaml: Tipps und Eskalation."""
    out = []
    for blk in advice["advice"]:
        for i, tip in enumerate(blk["tips"]):
            out += [(f"{blk['symptom_key']}.tips[{i}].{lang}", tip[lang]) for lang in ("cs", "en")]
    for kind in ("acute", "general"):
        out += [
            (f"escalation.{kind}.{lang}", advice["escalation"][kind][lang]) for lang in ("cs", "en")
        ]
    return out


def test_advice_covers_every_symptom_and_references_resolve(data: dict[str, Any]) -> None:
    items = {i["symptom_key"]: i for i in data["items.yaml"]["items"]}
    advice = data["advice.yaml"]
    assert advice["version"] == "advice-v1"
    keys = [b["symptom_key"] for b in advice["advice"]]
    assert len(keys) == len(set(keys)), "doppelter Tipp-Block je Symptom"
    assert set(keys) == set(items), "je Symptom aus items.yaml genau ein Tipp-Block"
    sources = {s["id"]: s for s in advice["sources"]}
    assert len(sources) == len(advice["sources"])
    for blk in advice["advice"]:
        sk = blk["symptom_key"]
        assert 2 <= len(blk["tips"]) <= 4, sk
        # min_value muss erreichbar sein: höchster Skalenwert des Symptoms (presence 1, sonst 4) ≥ min_value
        top = max(
            1 if a["attribute"] == "presence" else 4 for a in items[sk]["attributes"]
        )  # fmt: skip
        assert 1 <= blk["min_value"] <= top, sk
        assert blk["min_value"] == (1 if sk == "fever" else 2), (
            sk
        )  # Vorgabe T-12: Standard 2, Fieber 1
        assert blk["source_ids"] and set(blk["source_ids"]) <= set(sources), sk
        assert len({t["cs"] for t in blk["tips"]}) == len(blk["tips"]), sk
        assert all(t["cs"] != t["en"] for t in blk["tips"]), sk
    for s in sources.values():  # jeder Beleg mit Locator, URL (außer Klinik-PDF), Stufe B
        assert s["claim_level"] == "B" and s.get("locator"), s["id"]
        if s["id"] != "SRC-FNM-VYZVA3":
            assert s["url"].startswith(
                "https://www.cancer.gov/about-cancer/treatment/side-effects/"
            ), s["id"]
    unused = (
        set(sources)
        - {i for b in advice["advice"] for i in b["source_ids"]}
        - {advice["escalation"]["source_id"]}
    )
    assert not unused, f"Quelle ohne Verwendung: {unused}"


def test_escalation_follows_clinic_wording(data: dict[str, Any]) -> None:
    esc = data["advice.yaml"]["escalation"]
    assert esc["source_id"] == "SRC-FNM-VYZVA3"
    assert esc["ambulance_phone"] == "[telefon ambulance]"  # Platzhalter, klinikspezifisch
    for kind in ("acute", "general"):
        cs, en = esc[kind]["cs"], esc[kind]["en"]
        assert "ambulanci" in cs and "155" in cs and "akutních obtížích" in cs, kind
        assert "clinic" in en and "155" in en and "acute" in en, kind
    assert esc["acute"]["cs"] == "Při akutních obtížích kontaktujte ambulanci nebo volejte 155."
    # Quelle der Eskalation ist die Klinikvorgabe und steht im Quellenregister
    assert any(s["id"] == "SRC-FNM-VYZVA3" for s in data["advice.yaml"]["sources"])


def test_advice_texts_pass_all_forbidden_lists(data: dict[str, Any]) -> None:
    texts = _all_advice_texts(data["advice.yaml"])
    assert len(texts) >= 2 * (sum(len(b["tips"]) for b in data["advice.yaml"]["advice"]) + 2)
    for where, text in texts:
        lower = text.lower()
        is_escalation = where.startswith("escalation.")
        for (
            pat
        ) in FORBIDDEN:  # Liste aus T-01; "155" ist in der Eskalation Pflichtinhalt (Klinikvorgabe)
            if is_escalation and pat in (r"\b155\b",):
                continue
            assert not re.search(pat, text, re.IGNORECASE), f"{pat!r} in {where}: {text!r}"
        assert not [p for p in FORBIDDEN_FE if p in lower], (
            f"Frontend-Verbotsliste in {where}: {text!r}"
        )
        m = FORBIDDEN_A3.search(text)
        assert m is None, f"A3-Verbotsliste {m and m.group(0)!r} in {where}: {text!r}"
        m = FORBIDDEN_ADVICE_EXTRA.search(text)
        assert m is None, f"Medikament/Zusage {m and m.group(0)!r} in {where}: {text!r}"


def test_advice_forbidden_lists_detect_bad_phrases() -> None:
    """Gegenprobe: die Zusatzliste erkennt Medikamente, Dosierung und Reaktionszusagen."""
    for bad in (
        "Nehmen Sie 400 mg Ibuprofen.",
        "Vezměte si Imodium.",
        "Tým byl informován.",
        "Our team will be informed.",
        "Take two tablets daily.",
        "Přestaňte užívat lék.",
    ):
        assert FORBIDDEN_ADVICE_EXTRA.search(bad), bad


def test_frontend_forbidden_list_is_not_stale() -> None:
    """Gleicht die Kopie FORBIDDEN_FE mit forbidden.ts ab, sobald das Frontend im Repo liegt (sonst übersprungen)."""
    ts = CONTENT.parent / "frontend" / "waechter" / "i18n" / "forbidden.ts"
    if not ts.exists():
        pytest.skip(
            "challenge/frontend/waechter/i18n/forbidden.ts liegt auf diesem Stand nicht vor (NOT RUN)"
        )
    src = ts.read_text(encoding="utf-8")
    block = src.split("FORBIDDEN_PHRASES", 1)[1].split("];", 1)[0]
    phrases = _ts_string_lines(block)
    assert phrases, "forbidden.ts: keine Phrasen erkannt"
    assert phrases <= set(FORBIDDEN_FE), (
        f"forbidden.ts enthält Neues: {phrases - set(FORBIDDEN_FE)}"
    )


def _ts_string_lines(block: str) -> set[str]:
    """Zeilen der Form `'text',` bzw. `"text",` aus einem TypeScript-Array (Kommentare und Leerzeilen entfallen)."""
    phrases = set()
    for line in block.splitlines():
        s = line.strip().rstrip(",")
        if len(s) >= 2 and s[0] == s[-1] and s[0] in "'\"":
            phrases.add(s[1:-1])
    return phrases


def test_ts_string_line_parser() -> None:
    """Gegenprobe des Abgleichs: einfache und doppelte Anführungszeichen, Apostroph im Text, Kommentare."""
    block = "[\n  // Kommentar\n  'keine sorge',\n  \"don't worry\",\n  'alarm',\n"
    assert _ts_string_lines(block) == {"keine sorge", "don't worry", "alarm"}


def test_diagnoses_reference_items_and_cover_scenario(data: dict[str, Any]) -> None:
    items = {i["symptom_key"] for i in data["items.yaml"]["items"]}
    core = {i["symptom_key"] for i in data["items.yaml"]["items"] if i.get("core")}
    diag = data["diagnoses.yaml"]
    assert diag["version"] == "diagnoses-v1"
    groups = diag["diagnoses"]
    assert 3 <= len(groups) <= 6 and len({g["id"] for g in groups}) == len(
        groups
    )  # T-20: + PROSTATE, KIDNEY
    prefixes = [p for g in groups for p in g["icd10_prefixes"]]
    assert len(prefixes) == len(set(prefixes)), "ICD-Präfix in zwei Gruppen"
    for g in groups:
        assert set(g["symptom_keys"]) <= items, g["id"]  # nur Symptome aus items.yaml
        assert len(g["symptom_keys"]) <= 2, g[
            "id"
        ]  # Vorgabe T-12: höchstens 2 Zusatzsymptome je Gruppe
        assert not set(g["symptom_keys"]) & core, f"{g['id']}: Kernsymptome sind ohnehin enthalten"
        assert all(
            s["claim_level"] == "B" and s.get("locator") and s.get("url") for s in g["sources"]
        ), g["id"]
        if g["symptom_keys"]:  # Zusatz ohne Beleg wäre eine erfundene Fachregel
            assert any(s["id"].startswith("SRC-NCI-") for s in g["sources"]), (
                f"{g['id']}: Zusatzsymptome brauchen eine inhaltliche Quelle (nicht nur ICD)"
            )

    def group_of(code: str) -> str | None:
        hits = [g["id"] for g in groups if any(code.startswith(p) for p in g["icd10_prefixes"])]
        assert len(hits) <= 1, (code, hits)
        return hits[0] if hits else None

    # von Hand: Zuordnung der synthetischen Diagnosecodes (SYN-0001/3/4 kolorektal, 0002 Melanom, 0005 Mamma)
    expected = {
        "SYN-0001": "COLORECTAL", "SYN-0002": "MELANOMA", "SYN-0003": "COLORECTAL",
        "SYN-0004": "COLORECTAL", "SYN-0005": "BREAST", "SYN-0006": "PROSTATE", "SYN-0007": "KIDNEY",
    }  # fmt: skip
    keywords = {
        "COLORECTAL": "kolorekt", "MELANOMA": "melanom", "BREAST": "breast", "PROSTATE": "prostat", "KIDNEY": "ledvin",
    }  # fmt: skip
    regimens = {r["id"]: r for r in data["regimens.yaml"]["regimens"]}
    for p in data["scenario.yaml"]["patients"]:
        assert "diagnosis_code" in p, p["pseudonym"]
        assert group_of(p["diagnosis_code"]) == expected[p["pseudonym"]], p["pseudonym"]
        assert keywords[expected[p["pseudonym"]]] in p["diagnosis_text"].lower(), p["pseudonym"]
        # Invariante: die Diagnose fügt den Szenario-Patientinnen KEINE Frage hinzu ⇒ Antwortmengen und Orakel bleiben gültig
        gsym = set(next(g for g in groups if g["id"] == expected[p["pseudonym"]])["symptom_keys"])
        assert gsym <= core | set(regimens[p["regimen_id"]]["symptom_keys"]), p["pseudonym"]
    # mindestens eine Gruppe ohne Szenario-Patientin ist erlaubt (LUNG), eine Gruppe mit Zusatzsymptomen ist vorhanden
    assert any(g["symptom_keys"] for g in groups)


def test_schedule_is_consistent_and_honest(data: dict[str, Any]) -> None:
    sch = data["schedule.yaml"]
    assert sch["version"] == "schedule-v1"
    assert 1 <= sch["default_interval_days"] <= 14
    rules = {r["id"]: r for r in data["rules.yaml"]["rules"]}
    assert (
        sch["default_interval_days"] <= rules["R-MIS-01"]["params"]["max_days_without_response"]
    ), (
        "Standard-Intervall länger als die Grenze von R-MIS-01 ⇒ jede Patientin wäre vor der nächsten Fälligkeit „fehlend“"
    )
    cycle = min(r["cycle_length_days"] for r in data["regimens.yaml"]["regimens"])
    phases = sch["phases"]
    last_end = 0
    for ph in phases:
        assert ph["from_cycle_day"] <= ph["to_cycle_day"], ph
        assert ph["from_cycle_day"] > last_end, (
            f"Phasen überlappen oder sind nicht aufsteigend: {ph}"
        )
        assert ph["to_cycle_day"] <= cycle, f"Phase über Zykluslänge {cycle} hinaus: {ph}"
        last_end = ph["to_cycle_day"]
    text = (sch["rationale"]["cs"] + sch["rationale"]["en"]).lower()
    assert "klinicky neověřeno" in text and "not clinically validated" in text
    assert "klinika" in text and "clinic" in text  # festzulegen durch die Klinik
    assert sch["source_id"] == "SRC-BASCH-2017"


def test_regimens_cite_sukl_spc(data: dict[str, Any]) -> None:
    """Vertrag v1.9: Profile zitieren vorrangig die SPC aus der SÚKL-Datenbank (zentral zugelassene: die dort verlinkte EU-SPC)."""
    for r in data["regimens.yaml"]["regimens"]:
        sukl = [s for s in r["sources"] if s["id"].startswith("SRC-SUKL-")]
        assert sukl, f"{r['id']}: keine SÚKL-SPC-Quelle"
        for s in sukl:
            assert s["url"].startswith(
                (
                    "https://prehledy.sukl.cz/",
                    "https://www.ema.europa.eu/cs/documents/product-information/",
                )
            ), s["id"]
            assert "SÚKL" in s["title"] and "kodSUKL" in s["title"] and s["claim_level"] == "B", s[
                "id"
            ]
        cited = {n["source_id"] for n in r["watch_notes"]}
        assert cited & {s["id"] for s in sukl}, (
            f"{r['id']}: kein Hinweis stützt sich auf die SÚKL-SPC"
        )
        assert not [s for s in r["sources"] if s["id"].startswith("SRC-EMA-")], (
            f"{r['id']}: SRC-EMA-* wurde durch SRC-SUKL-* ersetzt"
        )


def test_every_source_id_is_registered_in_sources_md(data: dict[str, Any]) -> None:
    register = (CONTENT / "SOURCES.md").read_text(encoding="utf-8")
    used: set[str] = set()
    for r in data["regimens.yaml"]["regimens"]:
        used |= {s["id"] for s in r["sources"]}
    for g in data["diagnoses.yaml"]["diagnoses"]:
        used |= {s["id"] for s in g["sources"]}
    used |= {s["id"] for s in data["advice.yaml"]["sources"]}
    used |= {data["schedule.yaml"]["source_id"], data["advice.yaml"]["escalation"]["source_id"]}
    for sid in sorted(used):
        assert f"| {sid} |" in register, f"{sid} fehlt im Quellenregister SOURCES.md §1"


# --------------------------------------------------------------------------------------------------------------------
# T-20 / Vertrag v2.8 §13 (DR-033): Zielschemata C61/C64, SYN-0006/0007
# --------------------------------------------------------------------------------------------------------------------
T20_REGIMENS = {
    "ENZALUTAMIDE": ("ENZALUTAMIDE", "SRC-SUKL-XTANDI", "0194246", "L02BB04"),
    "ABIRATERONE": ("ABIRATERONE", "SRC-SUKL-ZYTIGA", "0168443", "L02BX03"),
    "PAZOPANIB": ("PAZOPANIB", "SRC-SUKL-VOTRIENT", "0167725", "L01EX03"),
    "NIVOLUMAB": ("NIVOLUMAB", "SRC-SUKL-OPDIVO", "0210772", "L01FF01"),
}
#: SHA-256 der kanonischen JSON-Darstellung von SYN-0001…0005 (Stand T-12): diese Patient:innen dürfen sich nie ändern.
#: Seit T-28 ohne `display_name` (Anzeigename = Login bzw. Pseudonym statt erfundener Namen); alle übrigen Felder sind
#: unverändert (Hash der T-12-Fassung ohne `display_name` = derselbe Wert).
SYN_1_TO_5_SHA256 = "ea5978873f9061cdb2e14fefc8f8b8e391ea80c50fd15952c2d65595fca5bd5f"
KNOWLEDGE = CONTENT.parent / "knowledge"
_FREQ_RANK = {
    "not known": 0,
    "very rare": 1,
    "rare": 2,
    "uncommon": 3,
    "common": 4,
    "very common": 5,
}


def test_syn_0001_to_0005_are_unchanged(data: dict[str, Any]) -> None:
    import hashlib

    patients = [
        {k: v for k, v in p.items() if k != "display_name"}
        for p in data["scenario.yaml"]["patients"][:5]
    ]
    canon = json.dumps(patients, sort_keys=True, ensure_ascii=False, default=str)
    assert hashlib.sha256(canon.encode("utf-8")).hexdigest() == SYN_1_TO_5_SHA256


def test_t20_regimens_are_derived_from_knowledge_matrix(data: dict[str, Any]) -> None:
    """Symptomprofil nur aus den SmPC-Zeilen (knowledge/ae_matrix.csv): therapiespezifische Schlüssel zuerst (Häufigkeit
    absteigend, dann alphabetisch), danach die Kern-Items; Quelle je Regime = SÚKL/EMA-SPC mit kodSUKL."""
    import csv

    items = data["items.yaml"]["items"]
    keys = {i["symptom_key"] for i in items}
    core = [i["symptom_key"] for i in items if i.get("core")]
    with open(KNOWLEDGE / "ae_matrix.csv", encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    regimens = {r["id"]: r for r in data["regimens.yaml"]["regimens"]}
    for rid, (sid, src_id, kod, atc) in T20_REGIMENS.items():
        best: dict[str, int] = {}
        for r in rows:
            if (
                r["substance_id"] == sid
                and r["patient_reportable"] == "yes"
                and r["pro_item"] in keys
            ):
                best[r["pro_item"]] = max(
                    best.get(r["pro_item"], 0), _FREQ_RANK[r["frequency_class"]]
                )
        specific = sorted(best, key=lambda k: (-best[k], k))
        expected = specific + [c for c in core if c not in specific]
        reg = regimens[rid]
        assert reg["symptom_keys"] == expected, rid
        assert reg["drugs"] == [{"name": sid.lower(), "atc": atc}], rid
        assert [s["id"] for s in reg["sources"]] == [src_id] and kod in reg["sources"][0][
            "title"
        ], rid
        assert reg["cycle_length_days"] == 28  # Demo-Annahme ANN-A1-11
        # Hinweise rein beschreibend: keine Dosis, Therapieänderung, Prognose oder Empfehlung
        for n in reg["watch_notes"]:
            text = n["text"]["cs"] + " " + n["text"]["en"]
            forbidden = r"\bmg\b|dávk|dose|dosage|doporuč|recommend|prognos|přerušit|interrupt"
            assert not re.search(forbidden, text, re.IGNORECASE), (rid, n["symptom_key"])


def test_t20_diagnoses_and_medications_reference_catalog() -> None:
    diag = {
        g["id"]: g
        for g in yaml.safe_load((CONTENT / "diagnoses.yaml").read_text(encoding="utf-8"))[
            "diagnoses"
        ]
    }
    assert diag["PROSTATE"]["icd10_prefixes"] == ["C61"] and diag["KIDNEY"]["icd10_prefixes"] == [
        "C64"
    ]
    assert (
        diag["PROSTATE"]["symptom_keys"] == [] and diag["KIDNEY"]["symptom_keys"] == []
    )  # keine Quelle für Zusätze
    regimens = {
        r["id"]: r
        for r in yaml.safe_load((CONTENT / "regimens.yaml").read_text(encoding="utf-8"))["regimens"]
    }
    meds = {
        m["id"]: m
        for m in yaml.safe_load((CONTENT / "medications.yaml").read_text(encoding="utf-8"))[
            "medications"
        ]
    }
    for rid, (_sid, src_id, kod, atc) in T20_REGIMENS.items():
        hits = [m for m in meds.values() if rid in m["regimen_ids"]]
        assert len(hits) == 1, rid
        m = hits[0]
        assert (m["sukl_code"], m["atc"], m["spc_source_id"], m["status"]) == (
            kod,
            atc,
            src_id,
            "draft",
        )
        assert src_id in {s["id"] for s in regimens[rid]["sources"]}
        assert m["atc"] == regimens[rid]["drugs"][0]["atc"]
    codes = [m["sukl_code"] for m in meds.values() if "sukl_code" in m]
    assert len(codes) == len(set(codes))


def test_t20_scenario_patients_follow_ticket(data: dict[str, Any]) -> None:
    pats = {p["pseudonym"]: p for p in data["scenario.yaml"]["patients"]}
    main, kidney = pats["SYN-0006"], pats["SYN-0007"]
    assert (main["diagnosis_code"], main["regimen_id"], main["sex"]) == (
        "C61",
        "ENZALUTAMIDE",
        "male",
    )
    assert (kidney["diagnosis_code"], kidney["regimen_id"]) == ("C64", "PAZOPANIB")
    assert "username" not in main and "username" not in kidney
    # Hauptfall Prostata: schleichende Müdigkeit als Trend (R-TRD-01, gelb) + genau eine rote Meldung
    levels = [(a["rule_id"], a["symptom_key"], a["level"]) for a in main["expected"]["alerts"]]
    assert sorted(levels) == [("R-TRD-01", "fatigue", "yellow"), ("R-URG-01", "fever", "red")]
    assert sum(1 for a in main["expected"]["alerts"] if a["level"] == "red") == 1
    # SYN-0007: Durchfall und Hand-Fuß gelb, keine rote Meldung
    assert {(a["symptom_key"], a["level"]) for a in kidney["expected"]["alerts"]} == {
        ("diarrhea", "yellow"),
        ("hand_foot", "yellow"),
    }
    assert kidney["expected"]["traffic_light_at_anchor"] == "yellow"
