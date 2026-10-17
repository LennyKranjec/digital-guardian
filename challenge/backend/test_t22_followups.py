"""T-22 (Vertrag v2.9): Folgefragen zu Freitext-Zuordnungen, kontrollierter Einfluss auf die Triage.

Das Sprachmodell bzw. der Wortlisten-Abgleich schlägt nur vor; erst die Antwort der Patientin auf
die Standardfrage ist eine normale Antwort (`source = free_text_followup`) und geht durch Regeln,
Triage, Beleg und Akut-Weiche. Echter Inhalt, feste Ankerzeit, kein Netz.
"""

# ruff: noqa: F401
import json
import uuid
from collections.abc import Sequence
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select

from conftest import CSRF
from test_t22_freetext import (
    BASE,
    Gateway,
    configure_openai,
    counts,
    post_text,
    real_content,
    respond,
    seeded_patient,
    session_client,
)
from waechter.models import Alert, Answer, FreeText, Patient, Response, TriageDecision
from waechter.services import freetext as service
from waechter.services.questionnaire import active_therapy

TEXT = "Mám PRŮJEM, bolí mě to a mám horečku."  # Durchfall, Schmerz, Fieber (template)


def followups_url(free_text_id: str) -> str:
    return f"{BASE}/me/free-text/{free_text_id}/answers"


def answer(
    client: TestClient,
    free_text_id: str,
    pairs: Sequence[tuple[str, str, int | None]],
    **extra: Any,
) -> Any:
    body = {
        "client_submission_id": str(uuid.uuid4()),
        "answers": [{"symptom_key": k, "attribute": a, "value": v} for k, a, v in pairs],
        **extra,
    }
    return client.post(followups_url(free_text_id), json=body)


def saved(client: TestClient, text: str = TEXT) -> dict[str, Any]:
    reply = post_text(client, respond(client), text)
    assert reply.status_code == 201, reply.text
    body: dict[str, Any] = reply.json()
    return body


def rows_of(app: FastAPI, model: Any, **where: Any) -> list[Any]:
    with app.state.session_factory() as session:
        return list(session.scalars(select(model).filter_by(**where)))


# --- Karten --------------------------------------------------------------------------------------


def test_every_checked_mapping_becomes_a_card_critical_symptoms_first(seeded_app: FastAPI) -> None:
    patient = session_client(seeded_app, "patient")
    cards = saved(patient)["followups"]
    assert [c["symptom_key"] for c in cards] == ["fever", "diarrhea", "pain"]
    assert [c["critical"] for c in cards] == [True, False, False]
    assert cards[0]["quote"] == "horečku"
    assert cards[1]["quote"] == "PRŮJEM"
    fever = cards[0]
    assert [q["attribute"] for q in fever["questions"]] == ["presence"]
    assert [q["attribute"] for q in cards[1]["questions"]] == ["frequency", "severity"]


def test_cards_use_the_same_question_texts_and_options_as_the_check_in(
    seeded_app: FastAPI,
) -> None:
    patient = session_client(seeded_app, "patient")
    cards = saved(patient)["followups"]
    for lang in ("cs", "en"):
        questionnaire = patient.get(f"{BASE}/me/questionnaire", params={"lang": lang}).json()
        standard = {
            (i["symptom_key"], q["attribute"]): (q["text"], q["options"])
            for i in questionnaire["items"]
            for q in i["questions"]
        }
        listed = patient.get(f"{BASE}/me/free-text/followups", params={"lang": lang}).json()
        assert listed
        for card in listed:
            for q in card["questions"]:
                key = (card["symptom_key"], q["attribute"])
                if key in standard:  # Symptom gehört zum Fragebogen: identischer Wortlaut
                    assert (q["text"], q["options"]) == standard[key]
    assert cards  # Gegenprobe: die Karten der Antwort selbst sind nicht leer


def test_cards_work_for_symptoms_outside_the_patients_questionnaire(seeded_app: FastAPI) -> None:
    patient = session_client(seeded_app, "patient")
    questionnaire = patient.get(f"{BASE}/me/questionnaire").json()
    tracked = {i["symptom_key"] for i in questionnaire["items"]}
    outside = {"hand_foot": "Dlaně a chodidla jsou červené", "rash": "Mám vyrážku"}
    key, text = next((k, t) for k, t in outside.items() if k not in tracked)
    body = saved(patient, text)
    assert [c["symptom_key"] for c in body["followups"]] == [key]
    pairs = [(key, q["attribute"], 1) for q in body["followups"][0]["questions"]]
    reply = answer(patient, body["free_text_id"], pairs)
    assert reply.status_code == 201, reply.text  # Katalog statt Fragebogen
    stored = rows_of(seeded_app, Response, source="free_text_followup")
    assert len(stored) == 1


def test_open_cards_list_survives_a_new_session_and_shrinks_with_every_answer(
    seeded_app: FastAPI,
) -> None:
    patient = session_client(seeded_app, "patient")
    body = saved(patient)
    again = patient.get(f"{BASE}/me/free-text/followups").json()
    assert [c["symptom_key"] for c in again] == ["fever", "diarrhea", "pain"]
    assert answer(patient, body["free_text_id"], [("fever", "presence", 0)]).status_code == 201
    left = patient.get(f"{BASE}/me/free-text/followups").json()
    assert [c["symptom_key"] for c in left] == ["diarrhea", "pain"]
    both = [("diarrhea", "frequency", 1), ("diarrhea", "severity", 1)]
    assert answer(patient, body["free_text_id"], both).status_code == 201
    assert [c["symptom_key"] for c in patient.get(f"{BASE}/me/free-text/followups").json()] == [
        "pain"
    ]


def test_partially_answered_card_only_asks_the_missing_attribute(seeded_app: FastAPI) -> None:
    patient = session_client(seeded_app, "patient")
    body = saved(patient)
    assert answer(patient, body["free_text_id"], [("diarrhea", "frequency", 2)]).status_code == 201
    card = next(
        c
        for c in patient.get(f"{BASE}/me/free-text/followups").json()
        if c["symptom_key"] == "diarrhea"
    )
    assert [q["attribute"] for q in card["questions"]] == ["severity"]


def test_skipping_a_follow_up_counts_as_answered_and_is_not_asked_again(
    seeded_app: FastAPI,
) -> None:
    patient = session_client(seeded_app, "patient")
    body = saved(patient)
    assert answer(patient, body["free_text_id"], [("fever", "presence", None)]).status_code == 201
    left = patient.get(f"{BASE}/me/free-text/followups").json()
    assert "fever" not in [c["symptom_key"] for c in left]


# --- Antwort = normale Antwort -------------------------------------------------------------------


def test_the_follow_up_answer_is_a_normal_response_with_source_lang_and_free_text(
    seeded_app: FastAPI,
) -> None:
    patient = session_client(seeded_app, "patient")
    body = saved(patient)
    reply = answer(patient, body["free_text_id"], [("diarrhea", "severity", 2)])
    assert reply.status_code == 201, reply.text
    receipt = reply.json()
    assert {"response_id", "recorded_at", "answered", "skipped", "message_key"} <= set(receipt)
    (stored,) = rows_of(seeded_app, Response, id=receipt["response_id"])
    assert stored.source == "free_text_followup"
    assert stored.free_text_id == body["free_text_id"]
    assert stored.lang == "cs"
    answers = rows_of(seeded_app, Answer, response_id=stored.id)
    assert [(a.symptom_key, a.attribute, a.value) for a in answers] == [("diarrhea", "severity", 2)]
    # Check-in-Antworten tragen die Standardherkunft
    others = [r for r in rows_of(seeded_app, Response) if r.id != stored.id]
    assert others
    assert all(r.source == "questionnaire" for r in others)


def test_a_severe_follow_up_answer_reaches_the_rules_but_the_free_text_alone_does_not(
    seeded_app: FastAPI,
) -> None:
    patient = session_client(seeded_app, "patient")
    body = saved(patient, "Mám silný průjem")
    before = counts(seeded_app)["wa_alerts"]
    reply = answer(patient, body["free_text_id"], [("diarrhea", "severity", 4)])
    assert reply.status_code == 201
    new = rows_of(seeded_app, Alert)
    assert counts(seeded_app)["wa_alerts"] > before  # die ANTWORT löst die Regel aus
    assert any(a.symptom_key == "diarrhea" and a.level == "red" for a in new)


def test_a_fever_follow_up_gets_the_acute_notice_in_its_receipt(seeded_app: FastAPI) -> None:
    patient = session_client(seeded_app, "patient")
    body = saved(patient, "Mám horečku")
    receipt = answer(patient, body["free_text_id"], [("fever", "presence", 1)]).json()
    assert receipt["escalation"]["level"] == "acute"  # Akut-Weiche über die Antwort
    assert "155" in receipt["escalation"]["text"]
    assert receipt["advice"] == []  # akut ⇒ keine Tipps für dieses Symptom


def test_the_follow_up_answer_is_triaged_on_top_of_the_last_check_in(seeded_app: FastAPI) -> None:
    patient = session_client(seeded_app, "patient")
    questionnaire = patient.get(f"{BASE}/me/questionnaire").json()
    full = [
        {"symptom_key": i["symptom_key"], "attribute": q["attribute"], "value": 0}
        for i in questionnaire["items"]
        for q in i["questions"]
    ]
    base = patient.post(
        f"{BASE}/me/responses",
        json={
            "client_submission_id": str(uuid.uuid4()),
            "questionnaire_id": questionnaire["questionnaire_id"],
            "answers": full,
        },
    ).json()
    text = post_text(patient, base["response_id"], "Mám průjem").json()
    receipt = answer(patient, text["free_text_id"], [("diarrhea", "severity", 3)]).json()
    decisions = {
        d.response_id: d for d in rows_of(seeded_app, TriageDecision, patient_id=_pid(seeded_app))
    }
    follow = decisions[receipt["response_id"]]
    assert follow.asked_questions >= len(full)  # Stand = letzter Check-in + Folgeantwort
    assert follow.incomplete is False  # nicht "unvollständig" wegen der Teilantwort
    assert follow.level in {"YELLOW", "RED"}  # Grad 3 bei Durchfall wirkt über den Baum
    assert decisions[base["response_id"]].level == "GREEN"


def _pid(app: FastAPI, pseudonym: str = "SYN-0001") -> str:
    return seeded_patient(app, pseudonym)


def test_follow_ups_are_never_the_comparison_state_of_the_next_check_in(
    seeded_app: FastAPI,
) -> None:
    """`previous_grades`: Folgefragen sind Teilantworten und nie der Vergleichsstand."""
    from datetime import UTC, datetime, timedelta

    from waechter.services import triage as triage_service

    t0 = datetime(2026, 10, 1, 9, 0, tzinfo=UTC)
    with seeded_app.state.session_factory() as session:
        patient = session.scalars(select(Patient).where(Patient.pseudonym == "SYN-0002")).one()
        kb = triage_service.get_kb()
        assert kb is not None
        profile = kb.profile(kb.regimen_profile[active_therapy(session, patient.id).regimen_id])
        made: list[Response] = []
        for index, (source, value) in enumerate(
            [("questionnaire", 1), ("free_text_followup", 3), ("questionnaire", 0)]
        ):
            response = Response(
                patient_id=patient.id,
                client_submission_id=f"cmp-{index}",
                channel="web",
                entered_by="self",
                recorded_at=t0 + timedelta(hours=index),
                questionnaire_id="items-v1",
                source=source,
            )
            session.add(response)
            session.flush()
            session.add(
                Answer(
                    response_id=response.id, symptom_key="fever", attribute="presence", value=value
                )
            )
            made.append(response)
        session.flush()
        previous = triage_service.previous_grades(session, made[2], profile)
    assert previous is not None
    assert previous["fever"] == 1  # Stand des Check-ins, nicht der Folgeantwort (3)


# --- Validierung, Idempotenz, Rechte -------------------------------------------------------------


def test_only_open_follow_up_fields_are_accepted(seeded_app: FastAPI) -> None:
    patient = session_client(seeded_app, "patient")
    body = saved(patient)
    unknown = answer(patient, body["free_text_id"], [("vomiting", "severity", 1)])
    assert unknown.status_code == 422
    assert unknown.json()["code"] == "followup_not_open"
    out_of_range = answer(patient, body["free_text_id"], [("fever", "presence", 2)])
    assert out_of_range.status_code == 422
    assert answer(patient, body["free_text_id"], [("fever", "presence", 1)]).status_code == 201
    again = answer(patient, body["free_text_id"], [("fever", "presence", 0)])
    assert again.status_code == 409
    assert again.json()["code"] == "followup_not_open"
    empty = patient.post(
        followups_url(body["free_text_id"]),
        json={"client_submission_id": str(uuid.uuid4()), "answers": []},
    )
    assert empty.status_code == 422


def test_replay_with_the_same_submission_id_returns_the_same_receipt(seeded_app: FastAPI) -> None:
    patient = session_client(seeded_app, "patient")
    body = saved(patient)
    csid = str(uuid.uuid4())
    payload = {
        "client_submission_id": csid,
        "answers": [{"symptom_key": "fever", "attribute": "presence", "value": 1}],
    }
    first = patient.post(followups_url(body["free_text_id"]), json=payload)
    second = patient.post(followups_url(body["free_text_id"]), json=payload)
    assert (first.status_code, second.status_code) == (201, 200)
    assert first.json() == second.json()
    assert len(rows_of(seeded_app, Response, source="free_text_followup")) == 1


def test_rights_foreign_free_text_404_roles_403_anonymous_401(seeded_app: FastAPI) -> None:
    patient, other = session_client(seeded_app, "patient"), session_client(seeded_app, "patient2")
    body = saved(patient)
    pair = [("fever", "presence", 1)]
    assert answer(other, body["free_text_id"], pair).status_code == 404  # IDOR
    assert answer(patient, str(uuid.uuid4()), pair).status_code == 404
    for username in ("doctor", "admin", "user"):
        assert (
            answer(session_client(seeded_app, username), body["free_text_id"], pair).status_code
            == 403
        )
    assert (
        answer(TestClient(seeded_app, headers=CSRF), body["free_text_id"], pair).status_code == 401
    )
    assert rows_of(seeded_app, Response, source="free_text_followup") == []
    assert other.get(f"{BASE}/me/free-text/followups").json() == []  # fremde Karten nie sichtbar


def test_followups_list_roles(seeded_app: FastAPI) -> None:
    url = f"{BASE}/me/free-text/followups"
    assert TestClient(seeded_app, headers=CSRF).get(url).status_code == 401
    assert session_client(seeded_app, "doctor").get(url).status_code == 403


def test_switched_off_flag_closes_the_follow_up_routes(
    seeded_app: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    patient = session_client(seeded_app, "patient")
    body = saved(patient)
    monkeypatch.setenv(service.FLAG_ENV, "0")
    assert answer(patient, body["free_text_id"], [("fever", "presence", 1)]).status_code == 409
    assert patient.get(f"{BASE}/me/free-text/followups").json() == []


# --- Proposed value, LLM, Klinik -----------------------------------------------------------------


def test_a_proposed_value_is_only_shown_to_the_doctor_and_never_stored_as_an_answer(
    seeded_app: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    reply = json.dumps(
        {
            "suggestions": [
                {
                    "symptom_key": "diarrhea",
                    "attribute": "severity",
                    "proposed_value": 4,
                    "quote": "průjem",
                },
                {
                    "symptom_key": "pain",
                    "attribute": "severity",
                    "proposed_value": 9,
                    "quote": "bolí",
                },
            ]
        }
    )
    configure_openai(monkeypatch, Gateway(reply))
    patient = session_client(seeded_app, "patient")
    response_id = respond(patient)
    before = counts(seeded_app)
    body = post_text(patient, response_id, "Mám průjem a bolí to").json()
    after = counts(seeded_app)
    assert (after["wa_answers"], after["wa_alerts"]) == (before["wa_answers"], before["wa_alerts"])
    (row,) = rows_of(seeded_app, FreeText)
    assert (row.mapper, row.mapper_mode) == ("openai:fake-deployment", "live")
    assert [(s["symptom_key"], s["proposed_value"]) for s in row.suggestions_json] == [
        ("diarrhea", 4)
    ]
    assert row.rejected_suggestions == 1  # proposed_value 9 liegt außerhalb des Bereichs
    pid = seeded_patient(seeded_app, "SYN-0001")
    listed = session_client(seeded_app, "doctor").get(f"{BASE}/patients/{pid}/free-texts").json()
    assert listed[0]["suggestions"][0]["proposed_value"] == 4
    assert [c["symptom_key"] for c in body["followups"]] == ["diarrhea"]  # Karte fragt ganz normal


def test_the_clinic_sees_confirmation_per_suggestion(seeded_app: FastAPI) -> None:
    patient = session_client(seeded_app, "patient")
    body = saved(patient)
    answer(patient, body["free_text_id"], [("fever", "presence", 1)])
    answer(
        patient, body["free_text_id"], [("diarrhea", "frequency", 2), ("diarrhea", "severity", 3)]
    )
    pid = seeded_patient(seeded_app, "SYN-0001")
    listed = session_client(seeded_app, "doctor").get(f"{BASE}/patients/{pid}/free-texts").json()
    by_key = {s["symptom_key"]: s for s in listed[0]["suggestions"]}
    assert by_key["fever"]["confirmed"] is True
    assert by_key["fever"]["answers"] == [{"attribute": "presence", "value": 1}]
    assert by_key["diarrhea"]["confirmed"] is True
    assert by_key["pain"]["confirmed"] is False
    assert by_key["pain"]["answers"] == []
    assert listed[0]["unconfirmed"] == 1


def test_the_worklist_marks_patients_with_unconfirmed_mappings(seeded_app: FastAPI) -> None:
    patient = session_client(seeded_app, "patient")
    body = saved(patient)
    doctor = session_client(seeded_app, "doctor")

    def unconfirmed() -> dict[str, int]:
        rows = doctor.get(f"{BASE}/patients").json()
        return {r["pseudonym"]: r.get("free_text_unconfirmed", 0) for r in rows}

    assert unconfirmed()["SYN-0001"] == 3
    assert unconfirmed()["SYN-0002"] == 0
    answer(patient, body["free_text_id"], [("fever", "presence", 0)])
    assert unconfirmed()["SYN-0001"] == 2
    answer(
        patient, body["free_text_id"], [("diarrhea", "frequency", 0), ("diarrhea", "severity", 0)]
    )
    answer(patient, body["free_text_id"], [("pain", "severity", 0), ("pain", "interference", 0)])
    assert unconfirmed()["SYN-0001"] == 0


def test_the_worklist_has_no_free_text_field_when_the_feature_is_off(
    seeded_app: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(service.FLAG_ENV, "0")
    rows = session_client(seeded_app, "doctor").get(f"{BASE}/patients").json()
    assert rows
    assert all("free_text_unconfirmed" not in r for r in rows)
