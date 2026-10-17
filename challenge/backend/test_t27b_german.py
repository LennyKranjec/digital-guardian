"""T-27b: deutsche Texte der Inhaltsdateien (advice/triage/rules/schedule) und fester Backend-Texte.

Jeder lokalisierte Text (Objekt mit `cs` und `en`) dieser vier Dateien trägt auch `de`; die deutsche
Oberfläche fällt nirgends auf Englisch zurück.
"""

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
import yaml
from fastapi import FastAPI

from app.main import create_app
from app.services import seed
from conftest import CHALLENGE_DIR, make_settings, migrate
from test_summary import BASE, REAL_CONTENT, staff
from waechter.constants import CONTENT_DIR_ENV
from waechter.llm.verifier import FORBIDDEN

FILES = ("advice.yaml", "triage.yaml", "rules.yaml", "schedule.yaml")
LANGS = ("cs", "en", "de")


def localized_texts(node: Any, path: str = "$") -> list[tuple[str, dict[str, Any]]]:
    """Alle Objekte mit `cs` und `en` (= LocalizedText) samt Pfad."""
    found: list[tuple[str, dict[str, Any]]] = []
    if isinstance(node, dict):
        if "cs" in node and "en" in node:
            found.append((path, node))
        for key, value in node.items():
            found.extend(localized_texts(value, f"{path}.{key}"))
    elif isinstance(node, list):
        for index, value in enumerate(node):
            found.extend(localized_texts(value, f"{path}[{index}]"))
    return found


def load(name: str) -> Any:
    return yaml.safe_load((CHALLENGE_DIR / "content" / name).read_text(encoding="utf-8"))


@pytest.mark.parametrize("name", FILES)
def test_every_localized_text_has_cs_en_and_de(name: str) -> None:
    texts = localized_texts(load(name))
    assert texts, name  # die Datei enthält lokalisierte Texte
    for path, text in texts:
        assert set(text) == set(LANGS), (name, path, sorted(text))
        for lang in LANGS:
            assert isinstance(text[lang], str), (name, path, lang)
            assert text[lang].strip(), (name, path, lang)


@pytest.mark.parametrize("name", FILES)
def test_german_is_a_translation_not_a_copy(name: str) -> None:
    for path, text in localized_texts(load(name)):
        assert text["de"].strip() != text["en"].strip(), (name, path)
        assert text["de"].strip() != text["cs"].strip(), (name, path)


def test_german_advice_stays_within_the_forbidden_word_list() -> None:
    """Die Verbotsliste (Diagnose, Empfehlung, Beruhigung, Ursache) gilt auch für de."""
    for path, text in localized_texts(load("advice.yaml")):
        assert FORBIDDEN.search(text["de"]) is None, (path, text["de"])


def test_german_advice_keeps_the_acute_reference_to_155() -> None:
    escalation = load("advice.yaml")["escalation"]
    for key in ("acute", "general"):
        assert "155" in escalation[key]["de"], key


# --- API in deutscher Sprache --------------------------------------------------------------------


@pytest.fixture(autouse=True)
def real_content(monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv(CONTENT_DIR_ENV, str(REAL_CONTENT))
    return REAL_CONTENT


@pytest.fixture(scope="module")
def real_app(tmp_path_factory: pytest.TempPathFactory) -> Iterator[FastAPI]:
    tmp_path: Path = tmp_path_factory.mktemp("t27b")
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv(CONTENT_DIR_ENV, str(REAL_CONTENT))
        settings = make_settings(tmp_path)
        migrate(settings)
        app = create_app(settings)
        with app.state.session_factory() as session:
            seed.provision(session, settings, app.state.registry, app.state.clock)
        yield app


def test_summary_and_facts_in_german_have_no_english_template_text(real_app: FastAPI) -> None:
    doctor = staff(real_app)
    rows = doctor.get(f"{BASE}/patients").json()
    assert len(rows) >= 5
    english_markers = ("Last visit", "Therapy:", "Open alert", "Patient response", "Clinician")
    for row in rows:
        patient = row["patient_id"]
        data = doctor.post(f"{BASE}/patients/{patient}/summary", params={"lang": "de"}).json()
        assert data["sentences"], row["pseudonym"]
        assert data["dropped_sentences"] == 0, row["pseudonym"]
        assert data["provenance"]["lang"] == "de"
        for sentence in data["sentences"]:
            assert not any(m in sentence["text"] for m in english_markers), sentence["text"]
            for ref in sentence["refs"]:
                fact = doctor.get(f"{BASE}/patients/{patient}/facts/{ref}", params={"lang": "de"})
                assert fact.status_code == 200, ref
                label = fact.json()["label"]
                assert not any(m in label for m in english_markers), label
                assert "skipped" not in str(fact.json()), ref


def test_alerts_in_german_use_the_german_rationale(real_app: FastAPI) -> None:
    doctor = staff(real_app)
    checked = 0
    for row in doctor.get(f"{BASE}/patients").json():
        url = f"{BASE}/patients/{row['patient_id']}/alerts"
        german = doctor.get(url, params={"lang": "de"}).json()
        english = {a["alert_id"]: a for a in doctor.get(url, params={"lang": "en"}).json()}
        for alert in german:
            other = english[alert["alert_id"]]
            assert alert["headline"] != other["headline"], alert["rule_id"]
            rationale = alert["explanation"]["rationale"]
            assert rationale, alert["rule_id"]
            assert rationale != other["explanation"]["rationale"], alert["rule_id"]
            checked += 1
    assert checked >= 3


def test_triage_config_and_assessment_texts_in_german(real_app: FastAPI) -> None:
    doctor = staff(real_app)
    german = doctor.get(f"{BASE}/config/triage", params={"lang": "de"})
    english = doctor.get(f"{BASE}/config/triage", params={"lang": "en"})
    assert german.status_code == english.status_code == 200
    assert german.text != english.text
    assert "Grad" in german.text
    assert "Symptom" in german.text


def test_notifications_follow_the_ui_language(real_app: FastAPI) -> None:
    doctor = staff(real_app)
    stored = doctor.get(f"{BASE}/notifications").json()
    german = {n["notification_id"]: n for n in doctor.get(f"{BASE}/notifications?lang=de").json()}
    english = {n["notification_id"]: n for n in doctor.get(f"{BASE}/notifications?lang=en").json()}
    assert stored
    assert set(german) == set(english) == {n["notification_id"] for n in stored}
    for row in stored:
        de, en = german[row["notification_id"]], english[row["notification_id"]]
        assert de["text"] != en["text"], row["notification_id"]
        assert de["text"].split(": ", 1)[0] == row["text"].split(": ", 1)[0]  # nur das Pseudonym
        assert {k: v for k, v in de.items() if k != "text"} == {
            k: v for k, v in row.items() if k != "text"
        }
    assert doctor.get(f"{BASE}/notifications?lang=fr").status_code == 422


def test_notifications_stay_staff_only(real_app: FastAPI) -> None:
    patient = staff(real_app, "patient")
    assert patient.get(f"{BASE}/notifications?lang=de").status_code == 403
