"""freetext.yaml (T-22a, Owner A1): Wortlisten und Warnwörter für den Freitext der Patientin.

Format und Lader gehören A2 (Schema `FreeTextFile`, `waechter/content.py`); das Schema prüft `test_content_schema.py` (FILES).
Hier: Abdeckung der 12 Symptome aus items.yaml, Dubletten und Mehrdeutigkeiten, Verbotsliste (nur Symptome, keine Diagnosebegriffe),
Mindestlängen und eingefrorene Beispiele gegen die ECHTE Treffer-Funktion (`waechter/freetext/text.py: find_terms`, per Dateipfad
geladen, damit der Test vom Backend-Paket unabhängig bleibt). Geprüft wird Softwareverhalten und Konsistenz der Listen,
NICHT fachliche Güte (die Listen sind Platzhalter/Annahmen, siehe SOURCES.md §10).
"""

from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml

CONTENT = Path(__file__).resolve().parent
CHALLENGE = CONTENT.parent
LANGS = ("cs", "en", "de")


def _load_text_module() -> Any:
    path = CHALLENGE / "backend" / "waechter" / "freetext" / "text.py"
    spec = importlib.util.spec_from_file_location("waechter_freetext_text_a1", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


TEXT = _load_text_module()
fold = TEXT.fold
find_terms = TEXT.find_terms


@pytest.fixture(scope="module")
def ft() -> dict:
    return yaml.safe_load((CONTENT / "freetext.yaml").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def items() -> dict:
    return yaml.safe_load((CONTENT / "items.yaml").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def sources_md() -> str:
    return (CONTENT / "SOURCES.md").read_text(encoding="utf-8")


def _terms(entry: dict) -> list[tuple[str, str]]:
    return [(lang, t) for lang in LANGS for t in entry["terms"].get(lang, [])]


def _symptom_terms(ft: dict, items: dict) -> dict[str, list[str]]:
    """Wie `mapper._terms_of`: Item-Labels cs/en + Synonyme aller Sprachen."""
    labels = {i["symptom_key"]: [i["label"]["cs"], i["label"]["en"]] for i in items["items"]}
    out = {k: list(v) for k, v in labels.items()}
    for entry in ft["synonyms"]:
        out[entry["symptom_key"]] += [t for _, t in _terms(entry)]
    return out


def analyze(text: str, ft: dict, items: dict) -> tuple[list[str], list[str]]:
    """(Symptome, Warnwort-IDs) wie Mapper (`template`) und `find_warnings` es liefern würden."""
    symptoms = sorted(
        k for k, terms in _symptom_terms(ft, items).items() if find_terms(text, terms)
    )
    return symptoms, warns_of(text, ft)


def warns_of(text: str, ft: dict) -> list[str]:
    """Wie `warning.find_warnings`: Begriffe aller Sprachen, IDs in Reihenfolge der Liste."""
    return [w["id"] for w in ft["warn_words"] if find_terms(text, [t for _, t in _terms(w)])]


# --------------------------------------------------------------------------------------------------------------------
# Abdeckung und Querverweise
# --------------------------------------------------------------------------------------------------------------------
def test_every_items_symptom_has_exactly_one_synonym_entry(ft: dict, items: dict) -> None:
    keys = [e["symptom_key"] for e in ft["synonyms"]]
    assert len(keys) == len(set(keys))
    assert set(keys) == {i["symptom_key"] for i in items["items"]}
    assert len(keys) == 12


def test_status_is_placeholder_and_assumption_is_stated(ft: dict) -> None:
    assert ft["status"] == "placeholder"
    for lang in ("cs", "en"):
        assert "klinicky" in ft["assumption"]["cs"] and "clinically" in ft["assumption"]["en"]
        assert ft["assumption"][lang]


def test_every_synonym_entry_has_cs_en_de_terms(ft: dict) -> None:
    for e in ft["synonyms"]:
        for lang in LANGS:
            assert len(e["terms"][lang]) >= 3, f"{e['symptom_key']}.{lang}: zu wenige Begriffe"
    ids = [w["id"] for w in ft["warn_words"]]
    assert len(ids) == len(set(ids)) and len(ids) >= 5
    for w in ft["warn_words"]:
        assert w.get("note"), f"{w['id']}: note (Herkunft/Grenze) fehlt"
        for lang in LANGS:
            assert len(w["terms"][lang]) >= 3, f"{w['id']}.{lang}"


def test_warn_groups_cover_the_agreed_topics(ft: dict) -> None:
    """A0-Beispiele (Atemnot, Brustschmerz, Blut im Stuhl, Fieber ab 38, Verwirrtheit) + Platzhaltergruppen von A2."""
    notes = " ".join(w["note"].lower() for w in ft["warn_words"])
    for topic in (
        "atemnot",
        "brust",
        "blut",
        "bewusstsein",
        "selbstverletzung",
        "verwirrtheit",
        "fieber",
    ):
        assert topic in notes, topic


# --------------------------------------------------------------------------------------------------------------------
# Dubletten, Mehrdeutigkeit, Mindestlängen
# --------------------------------------------------------------------------------------------------------------------
def test_no_duplicate_terms_within_or_across_symptoms(ft: dict) -> None:
    for lang in LANGS:
        owner: dict[str, str] = {}
        for e in ft["synonyms"]:
            folded = [fold(t) for t in e["terms"][lang]]
            assert len(folded) == len(set(folded)), (
                f"{e['symptom_key']}.{lang}: Dublette im Eintrag"
            )
            for f in folded:
                assert owner.setdefault(f, e["symptom_key"]) == e["symptom_key"], (
                    f"{lang}: {f!r} gehört zu {owner[f]!r} und {e['symptom_key']!r}"
                )
        for w in ft["warn_words"]:
            folded = [fold(t) for t in w["terms"][lang]]
            assert len(folded) == len(set(folded)), f"{w['id']}.{lang}: Dublette im Eintrag"
        seen: dict[str, str] = {}
        for w in ft["warn_words"]:
            for f in (fold(t) for t in w["terms"][lang]):
                assert seen.setdefault(f, w["id"]) == w["id"], (
                    f"{lang}: {f!r} in {seen[f]} und {w['id']}"
                )


def test_equal_length_terms_of_different_symptoms_are_distinguishable(ft: dict) -> None:
    """Zwei Symptome dürfen nicht dieselbe Wortfolge als Wortanfang beanspruchen (Beispiel: „nevoln“ bei Übelkeit und
    „nevolnost“ bei Erbrechen wären ununterscheidbar). Verschieden lange Begriffe sind unkritisch (mehrere Vorschläge erlaubt)."""
    for lang in LANGS:
        terms = [(e["symptom_key"], t) for e in ft["synonyms"] for t in e["terms"][lang]]
        for i, (k1, a) in enumerate(terms):
            for k2, b in terms[i + 1 :]:
                if k1 == k2 or len(a.split()) != len(b.split()):
                    continue
                hit_ab = any(s == 0 for s, _ in find_terms(b, [a]))
                hit_ba = any(s == 0 for s, _ in find_terms(a, [b]))
                assert not (hit_ab or hit_ba), f"{lang}: {a!r} ({k1}) und {b!r} ({k2}) überlappen"


#: Einwort-Begriffe mit nur 4 Zeichen sind riskant (A2: nicht „bol“); diese sind bewusst akzeptiert (Wortanfang ist eindeutig genug).
SHORT_ALLOWED = {
    "boli", "dlan", "afta", "afty", "sole", "palm", "puke", "itch", "ache", "hurt", "weak", "taub", "kotz", "juck", "gasp", "numb", "ubel", "unav", "brni", "mude", "pain", "rash",
}  # fmt: skip


def test_no_too_short_or_ambiguous_stems(ft: dict) -> None:
    for entry in [*ft["synonyms"], *ft["warn_words"]]:
        name = entry.get("symptom_key") or entry["id"]
        for lang, term in _terms(entry):
            f = fold(term).strip()
            assert 3 <= len(term) <= 40, f"{name}.{lang}: Länge {term!r}"
            if " " not in f and len(f) <= 4:
                assert f in SHORT_ALLOWED or len(f) > 4, (
                    f"{name}.{lang}: Einwort-Stamm {term!r} zu kurz/mehrdeutig"
                )
            assert f == " ".join(f.split()), f"{name}.{lang}: Leerraum in {term!r}"


def test_neutral_words_are_not_symptom_terms(ft: dict) -> None:
    """„chuť k jídlu“/„appetite“/„teplot“ allein sind neutral (auch „dobrá chuť“, „teplota 36,6“) und fehlen mit Absicht."""
    neutral = {
        "chut k jidlu",
        "appetite",
        "appetit",
        "teplot",
        "temperatur",
        "temperature",
        "hands and feet",
    }
    for e in ft["synonyms"]:
        for _, t in _terms(e):
            assert fold(t) not in neutral, t


def test_warn_words_use_phrases_not_bare_symptom_words(ft: dict) -> None:
    """Der Wortlisten-Abgleich kennt keine Verneinung: „dušnost nemám“ oder „bez horečky“ dürfen den Hinweis nicht auslösen."""
    bare = {
        "dusnost",
        "dusn",
        "horeck",
        "horecka",
        "fever",
        "fieber",
        "fiebrig",
        "pain",
        "bolest",
        "nausea",
        "dyspno",
    }
    for w in ft["warn_words"]:
        for lang, t in _terms(w):
            assert fold(t) not in bare, f"{w['id']}.{lang}: nacktes Symptomwort {t!r}"


# --------------------------------------------------------------------------------------------------------------------
# Verbotsliste: nur Symptome, keine Diagnose, keine Aussage zu Reaktion/Dringlichkeit
# --------------------------------------------------------------------------------------------------------------------
FORBIDDEN = re.compile(
    r"diagnos|diagnóz|nebezpe|danger|alarm|emergency|urgent|immediately|okamžit|no need to worry|don'?t worry|keine sorge|nemějte obav"
    r"|nic se neděje|will contact you|vás kontaktuje|we will call|call (your|the) doctor|zavolejte|\b112\b|\b155\b|vyhledejte"
    r"|seek (medical )?(help|care)|ampel|semafor|traffic|\bgrade\b|stupeň|ctcae",
    re.IGNORECASE,
)
DIAGNOSES = re.compile(
    r"infarkt|infarct|embol|pneumon|sepsis|sepse|neutropen|an[eé]mi|trombo|mrtvic|stroke|rakovin|cancer|karcinom|nádor|tumor"
    r"|infekc|infection|syndrom|syndrome|ileus|perforac|perforation|dehydrat|hypogly|hyperkal|hematurie|dermatit|ekz[eé]m|stomatit",
    re.IGNORECASE,
)


def test_terms_and_notes_contain_symptoms_only(ft: dict) -> None:
    strings = [t for e in [*ft["synonyms"], *ft["warn_words"]] for _, t in _terms(e)]
    strings += [w["note"] for w in ft["warn_words"]]
    assert len(strings) > 500
    for text in strings:
        assert not FORBIDDEN.search(text), f"Verbotsliste: {text!r}"
        assert not DIAGNOSES.search(text), f"Diagnosebegriff: {text!r}"


def test_file_has_no_patient_facing_notice_text(ft: dict) -> None:
    """Der Sofort-Hinweis ist advice.yaml escalation.acute; freetext.yaml führt keinen eigenen Hinweistext."""
    assert set(ft) == {"version", "status", "max_length", "assumption", "synonyms", "warn_words"}
    for w in ft["warn_words"]:
        assert set(w) == {"id", "terms", "note"}


# --------------------------------------------------------------------------------------------------------------------
# Herkunft: Fieber und Atemnot folgen advice.yaml always_acute_for; SPC-Begriffe stehen in items_draft.yaml
# --------------------------------------------------------------------------------------------------------------------
def test_always_acute_symptoms_are_reachable_by_a_warn_phrase(ft: dict, items: dict) -> None:
    advice = yaml.safe_load((CONTENT / "advice.yaml").read_text(encoding="utf-8"))
    assert set(advice["escalation"]["always_acute_for"]) == {"fever", "shortness_of_breath"}
    assert analyze("Nemůžu se nadechnout.", ft, items)[1] == ["FT-W-01"]
    assert analyze("Teplotu mám 38,5.", ft, items)[1] == ["FT-W-07"]


def test_spc_terms_come_from_knowledge_draft(ft: dict) -> None:
    """Die im Kopf von freetext.yaml als SPC-Begriff beanspruchten Wörter stehen in items_draft.yaml (original_terms_cs)."""
    draft = yaml.safe_load(
        (CHALLENGE / "knowledge" / "items_draft.yaml").read_text(encoding="utf-8")
    )
    spc = {fold(t) for r in draft["items"] if r["existing_item"] for t in r["original_terms_cs"]}
    claimed = {
        "fever": ["horečk", "pyrexi"], "shortness_of_breath": ["dyspno"], "diarrhea": ["průjem"], "vomiting": ["zvrac"],
        "nausea": ["nauze"], "fatigue": ["únav", "astenie"], "pain": ["bolest"], "mouth_sores": ["vředy v ústech"],
        "rash": ["vyrážk", "kopřivk"], "peripheral_neuropathy": ["parestez", "hypestez"],
        "decreased_appetite": ["snížená chuť k jídlu", "snížení chuti k jídlu"],
    }  # fmt: skip
    by_key = {e["symptom_key"]: [fold(t) for t in e["terms"]["cs"]] for e in ft["synonyms"]}
    for key, words in claimed.items():
        for w in words:
            assert fold(w) in by_key[key], f"{key}: {w!r} fehlt in freetext.yaml"
            assert any(s.startswith(fold(w)) for s in spc), (
                f"{key}: {w!r} steht nicht in items_draft.yaml original_terms_cs"
            )


# --------------------------------------------------------------------------------------------------------------------
# Eingefrorene Beispiele gegen die echte Treffer-Funktion (kein LLM, keine Verneinung)
# --------------------------------------------------------------------------------------------------------------------
#: (lang, Text, erwartete Symptome (sortiert), erwartete Warn-IDs, Anmerkung)
EXAMPLES = [
    ("cs", "Mám průjem a je mi nevolno.", ["diarrhea", "nausea"], [], ""),
    ("cs", "Chodím často na záchod.", ["diarrhea"], [], ""),
    ("cs", "Od rána mám horečku 38,5.", ["fever"], ["FT-W-07"], ""),
    ("cs", "Teplotu mám 38,5.", [], ["FT-W-07"], "Symptom wird nicht vorgeschlagen (nacktes „teplot“ fehlt bewusst), der Hinweis aber schon"),
    ("cs", "Teplotu mám 37,2.", [], [], "unter 38: kein Treffer"),
    ("cs", "Nemůžu se nadechnout.", ["shortness_of_breath"], ["FT-W-01"], ""),
    ("cs", "Dušnost nemám.", ["shortness_of_breath"], [], "KEIN Hinweis (nacktes Symptomwort ist kein Warnwort); als Vorschlag erscheint die Frage trotz Verneinung"),
    ("cs", "Bez horečky, ale bolí mě hlava.", ["fever", "pain"], [], "bekannte Grenze: keine Verneinungserkennung, „horečk“ schlägt als Vorschlag an"),
    ("cs", "Mám bolest na hrudi.", ["pain"], ["FT-W-02"], ""),
    ("cs", "Bolest v ústech, nemůžu pořádně jíst.", ["mouth_sores", "pain"], [], "beide Vorschläge (Wortanfang „bolest“ und „bolest v ústech“)"),
    ("cs", "Mám krev ve stolici.", [], ["FT-W-03"], ""),
    ("cs", "Na záchodě byla krev.", [], [], "bekannte Lücke: Umschreibung außerhalb der Liste"),
    ("cs", "Včera jsem omdlel.", [], ["FT-W-04"], ""),
    ("cs", "Poslední dny jsem zmatený.", [], ["FT-W-06"], ""),
    ("cs", "Brní mi prsty a mám pálení v ústech.", ["mouth_sores", "peripheral_neuropathy"], [], ""),
    ("cs", "Nemám chuť k jídlu a jsem unavená.", ["decreased_appetite", "fatigue"], [], ""),
    ("cs", "Mám dobrou chuť k jídlu.", [], [], "neutrales Wort löst nichts aus"),
    ("cs", "Měl jsem mdloby a vykašlávám krev.", [], ["FT-W-03", "FT-W-04"], ""),
    ("en", "I feel tired and have no appetite.", ["decreased_appetite", "fatigue"], [], ""),
    ("en", "High temperature since this morning, 39 degrees.", ["fever"], ["FT-W-07"], ""),
    ("en", "My hands tingle and I am short of breath.", ["peripheral_neuropathy", "shortness_of_breath"], [], "nur Vorschläge; „short of breath“ allein ist kein Warnwort"),
    ("en", "I can't breathe properly.", ["shortness_of_breath"], ["FT-W-01"], ""),
    ("en", "I fainted yesterday.", [], ["FT-W-04"], ""),
    ("en", "I was sick twice and now I feel sick.", ["nausea", "vomiting"], [], ""),
    ("en", "There was blood in my stool.", [], ["FT-W-03"], ""),
    ("en", "I have chest pain.", ["pain"], ["FT-W-02"], ""),
    ("en", "Sore mouth and a rash on my arms.", ["mouth_sores", "rash"], [], ""),
    ("en", "I have a good appetite.", [], [], "neutrales Wort löst nichts aus"),
    ("de", "Ich habe Durchfall und keine Luft.", ["diarrhea", "shortness_of_breath"], ["FT-W-01"], ""),
]  # fmt: skip


@pytest.mark.parametrize("case", EXAMPLES, ids=[f"{i:02d}" for i in range(len(EXAMPLES))])
def test_examples_against_real_matcher(
    ft: dict, items: dict, case: tuple[str, str, list[str], list[str], str]
) -> None:
    _, text, symptoms, warns, _note = case
    got_symptoms, got_warns = analyze(text, ft, items)
    assert got_symptoms == symptoms, f"{text!r}: Symptome {got_symptoms}"
    assert got_warns == warns, f"{text!r}: Warnwörter {got_warns}"


def test_every_warn_word_group_is_exercised(ft: dict) -> None:
    covered = {i for _, _, _, warns, _ in EXAMPLES for i in warns}
    missing = {w["id"] for w in ft["warn_words"]} - covered
    assert missing <= {"FT-W-05"}, (
        f"Warngruppen ohne Testfall: {missing}"
    )  # Selbstverletzung: sensibler Text, nur als Liste geprüft
    assert warns_of("I want to kill myself", ft) == ["FT-W-05"]


def test_matcher_has_no_negation_so_examples_document_the_limit() -> None:
    assert any("keine Verneinungserkennung" in n for *_, n in EXAMPLES)
    assert sum(1 for *_, n in EXAMPLES if "bekannte" in n) >= 2
