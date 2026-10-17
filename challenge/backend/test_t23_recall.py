"""T-23 (DR-041): Rückblick 7 Tage zu Beginn, danach täglich 24 h; Variante je Antwort."""

import uuid
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest
import yaml
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select

from conftest import login
from test_t16_triage import clear_history
from waechter.constants import CONTENT_DIR_ENV
from waechter.fhir import builder as fhir
from waechter.models import Answer, Response, Therapy
from waechter.services.questionnaire import RECALL_DAILY, RECALL_INITIAL

REAL = Path(__file__).resolve().parents[1] / "content"
BASE = "/api/v1/waechter"
QUESTIONNAIRE = f"{BASE}/me/questionnaire"
RESPONSES = f"{BASE}/me/responses"
SESSIONS = f"{BASE}/me/sessions"


@pytest.fixture(autouse=True)
def real_content(monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv(CONTENT_DIR_ENV, str(REAL))
    return REAL


def app_of(client: TestClient) -> FastAPI:
    application = client.app
    assert isinstance(application, FastAPI)
    return application


def submit_all(client: TestClient, value: int = 1) -> dict[str, Any]:
    """Beantwortet alle Fragen des aktuellen Fragebogens mit `value` (presence: 0)."""
    questionnaire = client.get(QUESTIONNAIRE, params={"lang": "cs"}).json()
    answers = [
        {
            "symptom_key": item["symptom_key"],
            "attribute": q["attribute"],
            "value": 0 if q["attribute"] == "presence" else value,
        }
        for item in questionnaire["items"]
        for q in item["questions"]
    ]
    reply = client.post(
        RESPONSES,
        json={
            "client_submission_id": str(uuid.uuid4()),
            "questionnaire_id": questionnaire["questionnaire_id"],
            "answers": answers,
        },
    )
    assert reply.status_code == 201, reply.text
    assert isinstance(questionnaire, dict)
    return questionnaire


def question_texts(questionnaire: dict[str, Any]) -> dict[tuple[str, str], str]:
    return {
        (item["symptom_key"], q["attribute"]): q["text"]
        for item in questionnaire["items"]
        for q in item["questions"]
    }


@pytest.mark.skip(reason="public version: official NCI PRO-CTCAE wording not shipped")
def test_first_questionnaire_uses_the_official_seven_day_wording(client: TestClient) -> None:
    clear_history(app_of(client), "SYN-0001")
    login(client, "patient")
    data = client.get(QUESTIONNAIRE, params={"lang": "cs"}).json()
    assert data["recall"] == RECALL_INITIAL
    assert "7 dnů" in data["recall_period"]
    texts = question_texts(data)
    assert texts[("fatigue", "severity")] == (
        "Jak ZÁVAŽNÁ byla během uplynulých 7 dnů Vaše NEJHORŠÍ ÚNAVA, "
        "VYČERPANOST NEBO NEDOSTATEK ENERGIE?"
    )
    en = client.get(QUESTIONNAIRE, params={"lang": "en"}).json()
    assert "over the past 7 days" in en["recall_period"]
    assert question_texts(en)[("nausea", "severity")] == (
        "In the last 7 days, what was the SEVERITY of your NAUSEA at its WORST?"
    )


@pytest.mark.skip(reason="public version: official NCI PRO-CTCAE wording not shipped")
def test_second_questionnaire_asks_for_24_hours_and_only_the_period_differs(
    client: TestClient,
) -> None:
    clear_history(app_of(client), "SYN-0001")
    login(client, "patient")
    first = submit_all(client)
    again = client.get(QUESTIONNAIRE, params={"lang": "cs"}).json()
    assert again["recall"] == RECALL_DAILY
    assert "24 hodin" in again["recall_period"]
    assert "7 dnů" not in again["recall_period"]
    initial, daily = question_texts(first), question_texts(again)
    assert first["questionnaire_id"] == again["questionnaire_id"]
    changed = 0
    for key, text in initial.items():
        if "7 dnů" in text:
            changed += 1
            assert daily[key] == text.replace("7 dnů", "24 hodin"), key
        else:
            assert daily[key] == text, key  # eigene Fragen (Fieber …) bleiben unverändert
    assert changed >= 6
    en = client.get(QUESTIONNAIRE, params={"lang": "en"}).json()
    assert all("24 hours" in t for k, t in question_texts(en).items() if "last" in t.lower())


def test_options_are_identical_in_both_recall_variants_and_languages(client: TestClient) -> None:
    clear_history(app_of(client), "SYN-0001")
    login(client, "patient")

    def option_values(data: dict[str, Any]) -> list[tuple[Any, ...]]:
        return [
            (item["symptom_key"], q["attribute"], tuple(o["value"] for o in q["options"]))
            for item in data["items"]
            for q in item["questions"]
        ]

    cs0 = client.get(QUESTIONNAIRE, params={"lang": "cs"}).json()
    en0 = client.get(QUESTIONNAIRE, params={"lang": "en"}).json()
    assert option_values(cs0) == option_values(en0)
    submit_all(client)
    cs1 = client.get(QUESTIONNAIRE, params={"lang": "cs"}).json()
    assert option_values(cs1) == option_values(cs0)
    for a, b in zip(cs1["items"], cs0["items"], strict=True):
        for qa, qb in zip(a["questions"], b["questions"], strict=True):
            assert [o["label"] for o in qa["options"]] == [o["label"] for o in qb["options"]]


def _shift_responses_back(application: FastAPI, patient_id: str, days: int) -> None:
    """Die feste Uhr stempelt Antworten auf „jetzt“; für Therapiewechsel-Fälle zurückschieben."""
    with application.state.session_factory() as session:
        for response in session.scalars(select(Response).where(Response.patient_id == patient_id)):
            response.recorded_at = response.recorded_at - timedelta(days=days)
        session.commit()


def _add_therapy(
    application: FastAPI, patient_id: str, regimen_id: str | None, days_from_now: int
) -> str:
    with application.state.session_factory() as session:
        current = session.scalars(
            select(Therapy)
            .where(Therapy.patient_id == patient_id)
            .order_by(Therapy.cycle_start.desc())
        ).first()
        assert current is not None
        regimen = regimen_id or current.regimen_id
        session.add(
            Therapy(
                patient_id=patient_id,
                regimen_id=regimen,
                cycle_start=application.state.clock.now() + timedelta(days=days_from_now),
                synthetic=True,
            )
        )
        session.commit()
        return regimen


def _other_regimen(current: str) -> str:
    regimens = yaml.safe_load((REAL / "regimens.yaml").read_text(encoding="utf-8"))["regimens"]
    return str(next(r["id"] for r in regimens if r["id"] != current))


def _current_regimen(application: FastAPI, patient_id: str) -> str:
    with application.state.session_factory() as session:
        return str(
            session.scalars(
                select(Therapy.regimen_id)
                .where(Therapy.patient_id == patient_id)
                .order_by(Therapy.cycle_start.desc())
            ).first()
        )


def test_regimen_change_restarts_with_the_seven_day_wording(client: TestClient) -> None:
    application = app_of(client)
    patient_id = clear_history(application, "SYN-0001")
    login(client, "patient")
    submit_all(client)
    assert client.get(QUESTIONNAIRE).json()["recall"] == RECALL_DAILY
    _shift_responses_back(application, patient_id, days=2)
    _add_therapy(
        application, patient_id, _other_regimen(_current_regimen(application, patient_id)), -1
    )
    assert client.get(QUESTIONNAIRE).json()["recall"] == RECALL_INITIAL


def test_new_cycle_of_the_same_regimen_does_not_restart(client: TestClient) -> None:
    application = app_of(client)
    patient_id = clear_history(application, "SYN-0001")
    login(client, "patient")
    submit_all(client)
    _shift_responses_back(application, patient_id, days=2)
    # neuer Zyklus desselben Regimes nach den Antworten: bleibt täglich (Lauf schon beantwortet)
    with application.state.session_factory() as session:
        first = session.scalars(
            select(Therapy).where(Therapy.patient_id == patient_id).order_by(Therapy.cycle_start)
        ).first()
        assert first is not None
        first.cycle_start = application.state.clock.now() - timedelta(days=5)
        session.commit()
    _add_therapy(application, patient_id, None, -1)
    assert client.get(QUESTIONNAIRE).json()["recall"] == RECALL_DAILY


def test_future_therapy_is_ignored(client: TestClient) -> None:
    application = app_of(client)
    patient_id = clear_history(application, "SYN-0001")
    login(client, "patient")
    submit_all(client)
    assert client.get(QUESTIONNAIRE).json()["recall"] == RECALL_DAILY
    _add_therapy(
        application, patient_id, _other_regimen(_current_regimen(application, patient_id)), 3
    )
    assert client.get(QUESTIONNAIRE).json()["recall"] == RECALL_DAILY


def test_client_can_send_the_variant_it_displayed(client: TestClient) -> None:
    application = app_of(client)
    patient_id = clear_history(application, "SYN-0001")
    login(client, "patient")
    questionnaire = client.get(QUESTIONNAIRE, params={"lang": "cs"}).json()
    assert questionnaire["recall"] == RECALL_INITIAL
    answers = [
        {"symptom_key": i["symptom_key"], "attribute": q["attribute"], "value": 0}
        for i in questionnaire["items"]
        for q in i["questions"]
    ]
    reply = client.post(
        RESPONSES,
        json={
            "client_submission_id": str(uuid.uuid4()),
            "questionnaire_id": questionnaire["questionnaire_id"],
            "answers": answers,
            "recall": RECALL_DAILY,  # der Client zeigte die Tagesfassung
        },
    )
    assert reply.status_code == 201, reply.text
    with application.state.session_factory() as session:
        stored = session.scalars(select(Response).where(Response.patient_id == patient_id)).one()
        assert stored.recall == RECALL_DAILY
    bad = client.post(
        RESPONSES,
        json={
            "client_submission_id": str(uuid.uuid4()),
            "questionnaire_id": questionnaire["questionnaire_id"],
            "answers": answers,
            "recall": "weekly",
        },
    )
    assert bad.status_code == 422


@pytest.mark.skip(reason="public version: official NCI PRO-CTCAE wording not shipped")
def test_variant_is_stored_with_every_response_and_answer(client: TestClient) -> None:
    application = app_of(client)
    patient_id = clear_history(application, "SYN-0001")
    login(client, "patient")
    submit_all(client)
    submit_all(client)
    with application.state.session_factory() as session:
        rows = session.scalars(select(Response).where(Response.patient_id == patient_id)).all()
        by_recall = {
            r.recall: r for r in rows
        }  # feste Uhr: gleicher Zeitpunkt, daher nicht nach Zeit sortieren
        assert sorted(by_recall) == [RECALL_DAILY, RECALL_INITIAL]
        assert len(rows) == 2
        first, second = (
            [
                (a.symptom_key, a.attribute, a.wording)
                for a in session.scalars(
                    select(Answer).where(Answer.response_id == by_recall[mode].id)
                )
            ]
            for mode in (RECALL_INITIAL, RECALL_DAILY)
        )
    assert {w for _, _, w in first} == {"official", "own"}
    assert {w for _, _, w in second} == {"adapted_recall", "own"}
    own = {(s, a) for s, a, w in first if w == "own"}
    assert ("fever", "presence") in own
    assert {(s, a) for s, a, w in second if w == "own"} == own  # eigene Items bleiben own


def test_fhir_response_carries_language_recall_and_wording() -> None:
    answer = fhir.AnswerData(
        answer_id="a1",
        symptom_key="nausea",
        attribute="severity",
        value=2,
        label="Nausea (severity)",
        option_label="Moderate",
        wording="adapted_recall",
    )
    response = fhir.ResponseData(
        response_id="r1",
        questionnaire_id="items-v1:X:none",
        recorded_at="2026-10-17T08:00:00+02:00",
        channel="web",
        entered_by="self",
        answers=[answer],
        lang="cs",
        recall=RECALL_DAILY,
    )
    data = fhir.ExportData(
        patient_id="p1",
        pseudonym="SYN-TEST",
        sex="f",
        birth_year=1970,
        language="cs",
        therapy_id=None,
        regimen_label="Test",
        cycle_start=None,
        drugs=[],
        generated_at="2026-10-17T08:00:00+02:00",
    )
    resource = fhir.questionnaire_response(data, response)
    tags = {(t["system"], t["code"]) for t in resource["meta"]["tag"]}
    assert ("urn:waechter:question-language", "cs") in tags
    assert ("urn:waechter:recall-period", "daily_24h") in tags
    # HAPI-Standardlauf kennt keine eigene Extension (A3): Wortlaut als meta.tag, nie als extension
    assert (fhir.WORDING_TAG_SYSTEM, "adapted_recall") in tags
    assert "extension" not in resource["item"][0]["item"][0]
    observation = fhir.pro_observation(data, response, answer)
    assert "extension" not in observation
    observation_tags = {(t["system"], t["code"]) for t in observation["meta"]["tag"]}
    assert ("urn:waechter:recall-period", "daily_24h") in observation_tags
    assert (fhir.WORDING_TAG_SYSTEM, "adapted_recall") in observation_tags
    legacy = fhir.ResponseData(
        response_id="r2",
        questionnaire_id="q",
        recorded_at="2026-10-17T08:00:00+02:00",
        channel="web",
        entered_by="self",
        answers=[],
    )
    assert not [
        t
        for t in fhir.questionnaire_response(data, legacy)["meta"]["tag"]
        if "recall" in t.get("system", "")
    ]


def test_adaptive_session_card_follows_the_same_recall_choice(client: TestClient) -> None:
    application = app_of(client)
    clear_history(application, "SYN-0001")
    login(client, "patient")
    first = client.post(SESSIONS, json={"client_session_id": str(uuid.uuid4()), "lang": "cs"})
    assert first.status_code == 201, first.text
    card = first.json()["next"]
    official = (
        "7 dnů" in card["text"]
    )  # die erste Karte kann ein eigenes Item sein (Fieber): dann ohne Rückblick
    submit_all(client)
    second = client.post(SESSIONS, json={"client_session_id": str(uuid.uuid4()), "lang": "cs"})
    assert second.status_code == 201, second.text
    text = second.json()["next"]["text"]
    assert "7 dnů" not in text
    if official:
        assert "24 hodin" in text
