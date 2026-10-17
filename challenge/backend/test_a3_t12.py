"""A3-Gegenproben zu T-12 (Besitz A3): Patiententexte (advice.yaml) und Diagnosegruppen.

Unabhängig von den Tests des Inhaltsautors: eigene Verbotsliste (COMMON §2, Patientenseite),
Medikamente und Dosierungen, Zusagen, Quellenverweise, Querverweise zu Symptomen und Szenario.
"""

import re
from pathlib import Path
from typing import Any

import pytest
import yaml

CONTENT = Path(__file__).resolve().parents[1] / "content"

FORBIDDEN = re.compile(
    r"ampel|semafor|traffic|alarm|\balert|červen|žlut|\bred\b|yellow|\bgrade\b|stupeň|ctcae"
    r"|diagnos|diagnóz|doporuč|recommend|empfehl|keine sorge|don.?t worry|no need to worry"
    r"|nemusíte se bát|v pořádku|alles in ordnung|all is (fine|well)|we will (contact|call)"
    r"|ozveme se|zavoláme|wir (melden|rufen)|notfall|emergency|nouz",
    re.IGNORECASE,
)
MEDICATION = re.compile(
    r"\b\d+[.,]?\d*\s?(mg|ml|µg|mcg|g)\b|ibuprofen|paracetamol|acetaminophen|aspirin|antibiot"
    r"|antipyret|analget|tablet|pilul|léčiv|medicat|\bdrugs?\b|\bdose|dávk|loperamid|imodium"
    r"|ondansetron",
    re.IGNORECASE,
)
REASSURANCE = re.compile(
    r"nebojte|nemusíte|není (to )?(nic|důvod)|bude (to )?(dobr|v pořádku)|normální|nothing to"
    r"|harmless|neškodn|\bsafe\b|bezpečn",
    re.IGNORECASE,
)
PROMISE = re.compile(
    r"ozve|zavol|we will|we'll|kontaktujeme|team will|do \d+ hodin|within \d+", re.I
)


def load(name: str) -> dict[str, Any]:
    data: dict[str, Any] = yaml.safe_load((CONTENT / name).read_text(encoding="utf-8"))
    return data


ADVICE = load("advice.yaml")
DIAGNOSES = load("diagnoses.yaml")
SCENARIO = load("scenario.yaml")
ITEMS = load("items.yaml")


def patient_texts() -> list[tuple[str, str]]:
    texts: list[tuple[str, str]] = []
    for kind, languages in ADVICE["escalation"].items():
        if isinstance(languages, dict):
            texts += [(f"escalation.{kind}.{lang}", text) for lang, text in languages.items()]
    for entry in ADVICE["advice"]:
        for index, tip in enumerate(entry["tips"]):
            texts += [(f"{entry['symptom_key']}[{index}].{lang}", t) for lang, t in tip.items()]
    return texts


def test_a3_advice_has_texts_in_both_languages_and_is_not_empty() -> None:
    texts = patient_texts()
    assert len(texts) >= 80
    for entry in ADVICE["advice"]:
        assert entry["tips"], entry["symptom_key"]
        for tip in entry["tips"]:
            assert set(tip) == {"cs", "en", "de"}, entry["symptom_key"]
            assert all(len(value.strip()) > 20 for value in tip.values())


@pytest.mark.parametrize(
    ("name", "pattern"),
    [
        ("Verbotsliste", FORBIDDEN),
        ("Medikament/Dosierung", MEDICATION),
        ("Beruhigung", REASSURANCE),
        ("Zusage", PROMISE),
    ],
)
def test_a3_patient_texts_contain_no_forbidden_content(name: str, pattern: re.Pattern[str]) -> None:
    hits = [(key, m.group(0)) for key, text in patient_texts() if (m := pattern.search(text))]
    assert hits == [], f"{name}: {hits}"


def test_a3_escalation_points_to_the_clinic_or_155_and_names_no_rating() -> None:
    for kind in ("acute", "general"):
        for lang, text in ADVICE["escalation"][kind].items():
            assert "155" in text, (kind, lang)
            assert re.search(r"ambulanc|ambulanz|outpatient clinic", text, re.I), (kind, lang)


def test_a3_every_advice_symptom_exists_and_the_threshold_is_on_the_scale() -> None:
    known = {item["symptom_key"] for item in ITEMS["items"]}
    for entry in ADVICE["advice"]:
        assert entry["symptom_key"] in known, entry["symptom_key"]
        assert 1 <= entry["min_value"] <= 4, entry["symptom_key"]
    keys = [entry["symptom_key"] for entry in ADVICE["advice"]]
    assert len(keys) == len(set(keys)), "Symptom doppelt"


def test_a3_advice_sources_resolve_and_carry_a_locator() -> None:
    sources = {s["id"]: s for s in ADVICE["sources"]}
    for entry in ADVICE["advice"]:
        assert entry["source_ids"], entry["symptom_key"]
        for source_id in entry["source_ids"]:
            assert source_id in sources, source_id
    for source in sources.values():
        assert source["locator"].strip(), source["id"]
        assert source["claim_level"] in {"A", "B", "C"}, source["id"]
        if "url" in source:
            assert source["url"].startswith("https://"), source["id"]
    assert ADVICE["escalation"]["source_id"] in sources


def test_a3_each_scenario_diagnosis_code_maps_to_exactly_one_group_and_matches_the_regimen() -> (
    None
):
    groups = {g["id"]: g for g in DIAGNOSES["diagnoses"]}
    # ICD-10 unabhängig: C18-C20 Kolorektum, C43 Melanom, C50 Mamma, C61 Prostata, C64 Niere
    expected = {"FOLFOX": "COLORECTAL", "CAPECITABINE": "COLORECTAL", "PEMBROLIZUMAB": "MELANOMA",
                "DOCETAXEL": "BREAST", "ENZALUTAMIDE": "PROSTATE", "ABIRATERONE": "PROSTATE",
                "PAZOPANIB": "KIDNEY", "NIVOLUMAB": "KIDNEY"}  # fmt: skip
    for patient in SCENARIO["patients"]:
        code = patient["diagnosis_code"]
        matches = [
            g["id"]
            for g in groups.values()
            if any(code.startswith(prefix) for prefix in g["icd10_prefixes"])
        ]
        assert len(matches) == 1, (patient["pseudonym"], code, matches)
        assert matches[0] == expected[patient["regimen_id"]], (patient["pseudonym"], matches)
    prefixes = [p for g in groups.values() for p in g["icd10_prefixes"]]
    assert len(prefixes) == len(set(prefixes)), "Präfix in mehreren Gruppen"


def test_a3_diagnosis_group_symptoms_exist() -> None:
    known = {item["symptom_key"] for item in ITEMS["items"]}
    for group in DIAGNOSES["diagnoses"]:
        assert set(group["symptom_keys"]) <= known, group["id"]
        for source in group["sources"]:
            assert source["locator"].strip()
