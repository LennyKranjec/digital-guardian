"""A3-Gegenprobe T-01 mit T-02/T-03: echter Inhalt (`challenge/content/`) gegen Lader, API.

Läuft erst, wenn Backend (T-02/T-03) und Inhalt (T-01) zusammen im Baum liegen. Besitz A3.
Keine Seed-Zahlen, kein Tagesdatum (Szenario-Anker, eingefrorene Uhr).
"""

import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.main import create_app
from app.services import seed
from conftest import CSRF, login, make_settings, migrate
from waechter.constants import CONTENT_DIR_ENV
from waechter.content import Content, load_content
from waechter.models import Answer, Patient, Response
from waechter.services.questionnaire import max_value, select_items

REAL = Path(__file__).resolve().parents[1] / "content"
QUESTIONNAIRE = "/api/v1/waechter/me/questionnaire"
RESPONSES = "/api/v1/waechter/me/responses"
LANGS = ("cs", "en", "de")

#: Verbotsliste Patientenseite (COMMON §2): Bewertung, Alarm, Diagnose, Beruhigung, Zusage
FORBIDDEN = re.compile(
    r"ampel|semafor|traffic|alarm|\balert|červen|žlut|\bred\b|yellow|\bgrade\b|stupeň|ctcae"
    r"|diagnos|doporuč|recommend|empfehl|keine sorge|don.?t worry|no need to worry"
    r"|nemusíte se bát|v pořádku|alles in ordnung|all is (fine|well)|we will (contact|call)"
    r"|ozveme se|zavoláme|wir (melden|rufen)|notfall|emergency|nouz",
    re.IGNORECASE,
)


@pytest.fixture(autouse=True)
def real_content(monkeypatch: pytest.MonkeyPatch) -> Path:
    """Überschreibt die Fixture-Welt der Backend-Tests mit dem echten Inhalt."""
    monkeypatch.setenv(CONTENT_DIR_ENV, str(REAL))
    return REAL


def _build_app(base: Path) -> FastAPI:
    settings = make_settings(base)
    migrate(settings)
    app = create_app(settings)
    with app.state.session_factory() as session:
        seed.provision(session, settings, app.state.registry, app.state.clock)
        session.commit()
    return app


@pytest.fixture
def real_app(tmp_path: Path) -> Any:
    """Frische Datenbank je Test (für Tests, die schreiben)."""
    app = _build_app(tmp_path)
    yield app
    app.state.engine.dispose()


@pytest.fixture(scope="module")
def real_app_ro(tmp_path_factory: pytest.TempPathFactory) -> Any:
    """Eine geseedete Datenbank je Modul (nur für lesende Tests; spart Seed-Zeit)."""
    with pytest.MonkeyPatch.context() as patch:
        patch.setenv(CONTENT_DIR_ENV, str(REAL))
        app = _build_app(tmp_path_factory.mktemp("ro"))
        yield app
        app.state.engine.dispose()


@pytest.fixture(scope="module")
def content() -> Content:
    return load_content(REAL)


def _texts(node: Any) -> list[str]:
    if isinstance(node, str):
        return [node]
    if isinstance(node, dict):
        return [t for v in node.values() for t in _texts(v)]
    if isinstance(node, list):
        return [t for v in node for t in _texts(v)]
    return []


# --- Lader und Schema -------------------------------------------------------------------------


def test_a3_real_content_loads_with_schema_and_cross_references(content: Content) -> None:
    pseudonyms = {p["pseudonym"] for p in content.scenario["patients"]}
    assert {"SYN-0001", "SYN-0002"} <= pseudonyms
    usernames = {p.get("username") for p in content.scenario["patients"]}
    assert {"patient", "patient2"} <= usernames  # G-14
    for patient in content.scenario["patients"]:
        assert patient["expected"]["traffic_light_at_anchor"] in {"red", "yellow", "green", "grey"}
        for alert in patient["expected"]["alerts"]:
            assert {"attribute", "level", "rule_id", "symptom_key"} <= set(alert)  # G-03


def test_a3_scale_labels_match_server_limits(content: Content) -> None:
    """Der Lader erzwingt es nicht: Beschriftungen je Attribut = Wertebereich des Servers."""
    for attribute, labels in content.items["scale_labels"].items():
        assert len(labels) == max_value(attribute) + 1, attribute
        assert all(label["cs"] and label["en"] for label in labels)


def test_a3_every_scenario_answer_belongs_to_the_patients_questionnaire(
    real_app_ro: FastAPI, content: Content
) -> None:
    with real_app_ro.state.session_factory() as session:
        for spec in content.scenario["patients"]:
            patient = session.scalars(
                select(Patient).where(Patient.pseudonym == spec["pseudonym"])
            ).one()
            allowed = select_items(session, patient.id, content).allowed_pairs()
            for response in spec["responses"]:
                for key, value in response["answers"].items():
                    symptom, attribute = key.split(".", 1)
                    assert (symptom, attribute) in allowed, (spec["pseudonym"], key)
                    if value is not None:
                        assert 0 <= value <= max_value(attribute), (spec["pseudonym"], key, value)


# --- Seed mit echtem Inhalt -------------------------------------------------------------------


def test_a3_seed_stores_all_scenario_responses_and_missing_as_null(
    real_app_ro: FastAPI, content: Content
) -> None:
    with real_app_ro.state.session_factory() as session:
        for spec in content.scenario["patients"]:
            patient = session.scalars(
                select(Patient).where(Patient.pseudonym == spec["pseudonym"])
            ).one()
            stored = session.scalars(
                select(Response).where(Response.patient_id == patient.id)
            ).all()
            assert len(stored) == len(spec["responses"]), spec["pseudonym"]
            nulls_planned = sum(v is None for r in spec["responses"] for v in r["answers"].values())
            nulls_stored = sum(
                a.value is None
                for r in stored
                for a in session.scalars(select(Answer).where(Answer.response_id == r.id))
            )
            assert nulls_stored == nulls_planned  # fehlend bleibt fehlend (nie 0)
            assert patient.synthetic is True


# --- Fragebogen je Konto und Sprache ----------------------------------------------------------


@pytest.mark.parametrize("username", ["patient", "patient2"])
def test_a3_questionnaire_is_complete_in_all_languages(real_app_ro: FastAPI, username: str) -> None:
    with TestClient(real_app_ro, headers=CSRF) as client:
        login(client, username)
        reference: list[tuple[str, str]] | None = None
        for lang in LANGS:
            body = client.get(QUESTIONNAIRE, params={"lang": lang}).json()
            assert body["recall_period"], lang
            assert body["selection_reason"], lang
            assert [i["source"] for i in body["items"]][:1] == ["core"]
            pairs = [
                (i["symptom_key"], q["attribute"]) for i in body["items"] for q in i["questions"]
            ]
            assert pairs, lang
            reference = reference or pairs
            assert pairs == reference  # gleiche Items in jeder Sprache
            for item in body["items"]:
                assert item["label"].strip(), (lang, item["symptom_key"])
                for question in item["questions"]:
                    assert question["text"].strip(), (lang, item["symptom_key"])
                    values = [o["value"] for o in question["options"]]
                    assert values == list(range(max_value(question["attribute"]) + 1))
                    assert all(o["label"].strip() for o in question["options"])


@pytest.mark.parametrize("username", ["patient", "patient2"])
def test_a3_every_offered_option_is_accepted_by_the_server(
    real_app: FastAPI, username: str
) -> None:
    with TestClient(real_app, headers=CSRF) as client:
        login(client, username)
        body = client.get(QUESTIONNAIRE).json()
        for value_index in range(5):
            answers = [
                {"symptom_key": i["symptom_key"], "attribute": q["attribute"], "value": o["value"]}
                for i in body["items"]
                for q in i["questions"]
                for o in q["options"]
                if o["value"] == value_index
            ]
            if not answers:
                continue
            response = client.post(
                RESPONSES,
                json={
                    "client_submission_id": str(uuid.uuid4()),
                    "questionnaire_id": body["questionnaire_id"],
                    "answers": answers,
                },
            )
            assert response.status_code == 201, (value_index, response.text)


# --- Patiententexte (B5: ohne Ampel, Grad, Beruhigung, Alarm, Diagnose, Reaktionszusage) -------


@pytest.mark.parametrize("username", ["patient", "patient2"])
def test_a3_patient_facing_texts_pass_the_forbidden_list(
    real_app_ro: FastAPI, username: str
) -> None:
    with TestClient(real_app_ro, headers=CSRF) as client:
        login(client, username)
        for lang in LANGS:
            body = client.get(QUESTIONNAIRE, params={"lang": lang}).json()
            for text in _texts(body):
                match = FORBIDDEN.search(text)
                assert match is None, (lang, match and match.group(0), text)


def test_a3_forbidden_list_actually_matches_bad_phrases() -> None:
    """Gegenprobe zur Verbotsliste (Mutationsprobe): schlechte Sätze werden erkannt."""
    for bad in (
        "Alles in Ordnung, keine Sorge.",
        "Your status is red.",
        "Wir melden uns bei Ihnen.",
        "Nemusíte se bát.",
        "Grade 3 nausea",
        "Dies ist keine Diagnose",
    ):
        assert FORBIDDEN.search(bad), bad


# --- Bereitschaft für E2E-1 (SYN-0002 / patient2, Fieber = 1 ⇒ R-URG-01 rot) -------------------


def test_a3_e2e_precondition_patient2_can_trigger_a_red_fever_rule(
    real_app: FastAPI, content: Content
) -> None:
    spec = next(p for p in content.scenario["patients"] if p["pseudonym"] == "SYN-0002")
    assert spec["expected"]["traffic_light_at_anchor"] == "green"
    assert all(e["level"] != "red" for e in spec["expected"]["alerts"])  # keine offene rote Meldung
    rule = next(r for r in content.rules["rules"] if r["id"] == "R-URG-01")
    assert rule["enabled"]
    assert (rule["level"], rule["kind"]) == ("red", "threshold")
    assert rule["params"]["min_value"] == 1
    assert rule["symptom_keys"] == ["fever"]
    assert rule["attributes"] == ["presence"]
    with TestClient(real_app, headers=CSRF) as client:
        login(client, "patient2")
        body = client.get(QUESTIONNAIRE, params={"lang": "cs"}).json()
        fever = next(i for i in body["items"] if i["symptom_key"] == "fever")
        presence = next(q for q in fever["questions"] if q["attribute"] == "presence")
        assert [o["value"] for o in presence["options"]] == [0, 1]
        receipt = client.post(
            RESPONSES,
            json={
                "client_submission_id": str(uuid.uuid4()),
                "questionnaire_id": body["questionnaire_id"],
                "answers": [{"symptom_key": "fever", "attribute": "presence", "value": 1}],
            },
        )
        assert receipt.status_code == 201


# --- Seed-Meldungen gegen das unabhängige A3-Orakel (nicht `expected`, nicht A1/A2-Code) ---


def _load_oracle() -> Any:
    import importlib.util

    path = Path(__file__).resolve().parents[2] / "docs" / "verification" / "tools" / "oracle_a3.py"
    spec = importlib.util.spec_from_file_location("oracle_a3", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_a3_seeded_alerts_equal_the_independent_oracle(
    real_app_ro: FastAPI, content: Content
) -> None:
    from waechter.models import Alert
    from waechter.timeutil import to_prague

    oracle = _load_oracle()
    anchor = datetime.fromisoformat(content.scenario["anchor"])
    with real_app_ro.state.session_factory() as session:
        for spec in content.scenario["patients"]:
            expected, _ = oracle.evaluate(content.rules, content.scenario, spec)
            patient = session.scalars(
                select(Patient).where(Patient.pseudonym == spec["pseudonym"])
            ).one()
            stored = sorted(
                (
                    (to_prague(a.created_at).date() - to_prague(anchor).date()).days,
                    to_prague(a.created_at).hour,
                    a.rule_id,
                    a.symptom_key,
                    a.attribute,
                    a.level,
                )
                for a in session.scalars(select(Alert).where(Alert.patient_id == patient.id))
            )
            assert stored == expected, spec["pseudonym"]


class _StepClock:
    def __init__(self, instant: datetime) -> None:
        self.instant = instant

    def now(self) -> datetime:
        return self.instant


def test_a3_recovery_of_a_different_symptom_with_the_same_attribute_does_not_end_the_episode(
    real_app: FastAPI,
) -> None:
    """DR-012 gilt je Tripel: eine Durchfall-Entwarnung beendet nicht die Übelkeits-Episode."""
    from datetime import UTC, timedelta

    from waechter.models import Alert

    start = datetime(2026, 10, 18, 9, 0, tzinfo=UTC)
    clock = _StepClock(start)
    real_app.state.clock = clock

    def nausea_alerts() -> int:
        with real_app.state.session_factory() as session:
            patient = session.scalars(select(Patient).where(Patient.pseudonym == "SYN-0002")).one()
            return len(
                session.scalars(
                    select(Alert).where(
                        Alert.patient_id == patient.id,
                        Alert.symptom_key == "nausea",
                        Alert.rule_id == "R-SEV-01",
                    )
                ).all()
            )

    with TestClient(real_app, headers=CSRF) as client:
        login(client, "patient2")
        qid = client.get(QUESTIONNAIRE).json()["questionnaire_id"]

        def submit(symptom: str, value: int) -> None:
            body = {
                "client_submission_id": str(uuid.uuid4()),
                "questionnaire_id": qid,
                "answers": [{"symptom_key": symptom, "attribute": "severity", "value": value}],
            }
            assert client.post(RESPONSES, json=body).status_code == 201

        submit("nausea", 3)
        first = nausea_alerts()
        assert first == 1
        clock.instant = start + timedelta(hours=1)
        submit("diarrhea", 0)  # anderes Symptom, gleiche Attributart
        clock.instant = start + timedelta(hours=2)
        submit("nausea", 3)
        assert nausea_alerts() == first  # Episode nicht beendet ⇒ keine neue Meldung
        clock.instant = start + timedelta(hours=3)
        submit("nausea", 0)  # echte Entwarnung desselben Tripels
        clock.instant = start + timedelta(hours=4)
        submit("nausea", 3)
        assert nausea_alerts() == first + 1


def test_a3_worklist_lights_and_order_equal_the_independent_oracle(
    real_app_ro: FastAPI, content: Content
) -> None:
    """Arbeitsliste am Anker: Ampel je Patientin = unabhängiges Orakel; Reihenfolge nach Vertrag."""
    oracle = _load_oracle()
    expected = {
        p["pseudonym"]: oracle.evaluate(content.rules, content.scenario, p)[1]
        for p in content.scenario["patients"]
    }
    with TestClient(real_app_ro, headers=CSRF) as client:
        login(client, "doctor")
        rows = client.get("/api/v1/waechter/patients").json()
    assert {r["pseudonym"]: r["traffic_light"] for r in rows} == expected
    rank = {"red": 3, "yellow": 2, "grey": 1, "green": 0}
    assert [rank[r["traffic_light"]] for r in rows] == sorted(
        (rank[r["traffic_light"]] for r in rows), reverse=True
    )
    assert all(r["synthetic"] is True for r in rows)
