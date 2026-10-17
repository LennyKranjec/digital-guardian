"""T-22 (Vertrag v2.9): Freitext der Patientin: Vorschlag, Prüfer, Warnwörter, Dauerhaftigkeit.

Echter Inhalt (`challenge/content`, `freetext.yaml` ist Platzhalter), feste Ankerzeit, kein Netz.
Grundregel in jedem Test: Freitext erzeugt nie Antworten, Stufen, Entscheidungen oder Meldungen.
"""

import json
import urllib.error
import uuid
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.persistence.models import AuditEvent
from conftest import CSRF, login
from waechter.constants import CONTENT_DIR_ENV
from waechter.content import Content, load_content
from waechter.freetext import mapper, verify
from waechter.freetext.mapper import Candidate
from waechter.freetext.text import clean_text, find_quote, find_terms, fold
from waechter.llm import adapters
from waechter.models import (
    Alert,
    Answer,
    FreeText,
    Notification,
    Patient,
    Response,
    TriageDecision,
)
from waechter.services import freetext as service

REAL = Path(__file__).resolve().parents[1] / "content"
BASE = "/api/v1/waechter"
SECRET = "schluessel-ft-1"  # noqa: S105 (Testwert)


@pytest.fixture(autouse=True)
def real_content(monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv(CONTENT_DIR_ENV, str(REAL))
    monkeypatch.delenv(service.FLAG_ENV, raising=False)
    return REAL


@pytest.fixture(scope="module")
def content() -> Content:
    return load_content(REAL)


CATALOG = {
    "diarrhea": ("frequency", "severity"),
    "pain": ("severity", "interference"),
    "fever": ("presence",),
}


def candidates() -> list[Candidate]:
    return [
        Candidate("diarrhea", "Průjem", "Diarrhea", ("frequency", "severity"), True),
        Candidate("pain", "Bolest", "Pain", ("severity", "interference"), True),
        Candidate("fever", "Horečka", "Fever", ("presence",), False),
    ]


# --- Textwerkzeuge -------------------------------------------------------------------------------


def test_fold_keeps_the_length_and_drops_diacritics_and_case() -> None:
    text = "Průjem ČÁSTO - Übelkeit ß \u2018x\u2019"
    folded = fold(text)
    assert len(folded) == len(text)
    assert folded.startswith("prujem casto")
    assert "ubelkeit" in folded
    assert folded.endswith("'x'")  # typografische Apostrophe


def test_find_terms_matches_word_starts_not_inside_words() -> None:
    text = "Mám PRŮJMY a pozdní průjem"
    spans = find_terms(text, ["průjm"])
    assert [text[a:b] for a, b in spans] == ["PRŮJMY"]  # "průjem" hat anderen Stamm
    assert find_terms("nebolest", ["bolest"]) == []  # nicht mitten im Wort
    assert find_terms("bolest", ["bo"]) == []  # zu kurzer Stamm zählt nicht


def test_find_terms_allows_any_whitespace_between_words_and_merges_overlaps() -> None:
    text = "mám   bolest\nv ústech a bolest"
    spans = find_terms(text, ["bolest v ústech", "bolest"])
    assert [text[a:b].split() for a, b in spans] == [["bolest", "v", "ústech"], ["bolest"]]


def test_find_quote_is_verbatim_modulo_case_and_whitespace_but_not_diacritics() -> None:
    text = "Mám Průjem  a\nbolest"
    assert find_quote(text, "průjem a bolest") == (4, len(text))
    assert find_quote(text, "prujem") is None  # Diakritika zählen
    assert find_quote(text, "   ") is None
    assert find_quote(text, "kašel") is None


def test_clean_text_normalizes_line_ends_and_removes_control_characters() -> None:
    assert clean_text("  a\r\nb\rc\x00\x07d  ") == "a\nb\ncd"


# --- Prüfer --------------------------------------------------------------------------------------


def test_verifier_keeps_a_verbatim_quote_with_original_text_and_position() -> None:
    text = "Dnes mám PRŮJEM a horečku"
    result = verify.verify_suggestions(
        text, [{"symptom_key": "diarrhea", "quote": "průjem"}], CATALOG
    )
    (only,) = result.suggestions
    assert (only.quote, only.start, only.end) == ("PRŮJEM", 9, 15)
    assert text[only.start : only.end] == only.quote
    assert result.rejected == 0


@pytest.mark.parametrize(
    "raw",
    [
        {"symptom_key": "diarrhea", "quote": "kašel"},  # erfundenes Zitat
        {"symptom_key": "diarrhea", "quote": "prujem"},  # nicht wörtlich (Diakritika)
        {"symptom_key": "kaslik", "quote": "průjem"},  # unbekanntes Symptom
        {"symptom_key": "diarrhea", "attribute": "interference", "quote": "průjem"},  # Attribut
        {"symptom_key": "diarrhea", "quote": "průjem", "severity": 3},  # zusätzliches Feld
        {"symptom_key": "diarrhea"},  # Zitat fehlt
        {"quote": "průjem"},  # Symptom fehlt
        {"symptom_key": "diarrhea", "quote": "p"},  # zu kurz
        {"symptom_key": "diarrhea", "quote": "x" * 201},  # zu lang
        {"symptom_key": 7, "quote": "průjem"},
        "průjem",
        None,
    ],
)
def test_verifier_rejects_invented_quotes_unknown_symptoms_and_bad_shapes(raw: Any) -> None:
    result = verify.verify_suggestions("Dnes mám průjem", [raw], CATALOG)
    assert result.suggestions == ()
    assert result.rejected == 1


def test_verifier_accepts_a_known_attribute_dedupes_and_sorts_by_position() -> None:
    text = "bolest a průjem, průjem"
    raw = [
        {"symptom_key": "diarrhea", "attribute": "severity", "quote": "průjem"},
        {"symptom_key": "pain", "attribute": None, "quote": "bolest"},
        {"symptom_key": "diarrhea", "attribute": "severity", "quote": "PRŮJEM"},  # gleiche Stelle
    ]
    result = verify.verify_suggestions(text, raw, CATALOG)
    assert [(s.symptom_key, s.attribute, s.start) for s in result.suggestions] == [
        ("pain", None, 0),
        ("diarrhea", "severity", 9),
    ]


def test_verifier_caps_the_number_of_suggestions() -> None:
    words = [f"wort{i:02d}" for i in range(12)]
    catalog = {f"s{i}": ("severity",) for i in range(12)}
    raw = [{"symptom_key": f"s{i}", "quote": w} for i, w in enumerate(words)]
    result = verify.verify_suggestions(" ".join(words), raw, catalog)
    assert len(result.suggestions) == verify.MAX_SUGGESTIONS
    assert result.rejected == 12 - verify.MAX_SUGGESTIONS


# --- Adapter -------------------------------------------------------------------------------------


def test_template_mapper_maps_by_word_list_and_labels(content: Content) -> None:
    text = "Od včera mám PRŮJEM, bolí mě to a mám horečku"
    raw = mapper.template_map(text, candidates(), content.freetext)
    found = {(r["symptom_key"], r["quote"]) for r in raw}
    assert found == {("diarrhea", "PRŮJEM"), ("pain", "bolí"), ("fever", "horečku")}
    verified = verify.verify_suggestions(text, raw, CATALOG)
    assert [s.symptom_key for s in verified.suggestions] == ["diarrhea", "pain", "fever"]
    assert verified.rejected == 0


def test_template_mapper_without_a_word_file_uses_the_item_labels_only() -> None:
    raw = mapper.template_map("Horečka od rána", candidates(), None)
    assert [(r["symptom_key"], r["quote"]) for r in raw] == [("fever", "Horečka")]


class Gateway:
    """Ersetzt `adapters._urlopen`: liefert eine Gateway-Antwort ohne Netz."""

    def __init__(self, answer: str | None) -> None:
        self.answer = answer
        self.prompts: list[str] = []

    def __call__(self, request: Any, timeout: float = 0) -> Any:
        self.prompts.append(request.data.decode("utf-8"))
        if self.answer is None:
            raise urllib.error.HTTPError(request.full_url, 404, "DeploymentNotFound", None, None)  # type: ignore[arg-type]
        body = json.dumps({"output_text": self.answer}).encode()

        class Response:
            def __enter__(self) -> "Response":
                return self

            def __exit__(self, *args: object) -> None:
                return None

            def read(self) -> bytes:
                return body

        return Response()


def configure_openai(monkeypatch: pytest.MonkeyPatch, gateway: Gateway) -> None:
    monkeypatch.setenv("WAECHTER_LLM", "openai")
    monkeypatch.setenv("WAECHTER_LLM_BASE_URL", "https://gateway.invalid/v1")
    monkeypatch.setenv("WAECHTER_LLM_API_KEY", SECRET)
    monkeypatch.setenv("WAECHTER_LLM_MODEL", "fake-deployment")
    monkeypatch.setattr(adapters, "_urlopen", gateway)


def test_llm_mapper_is_live_and_its_output_still_goes_through_the_verifier(
    monkeypatch: pytest.MonkeyPatch, content: Content
) -> None:
    answer = json.dumps(
        {
            "suggestions": [
                {"symptom_key": "diarrhea", "attribute": None, "quote": "PRŮJEM"},
                {"symptom_key": "pain", "attribute": None, "quote": "erfundenes Zitat"},
                {"symptom_key": "kaslik", "attribute": None, "quote": "mám"},
            ]
        }
    )
    gateway = Gateway(f"```json\n{answer}\n```")
    configure_openai(monkeypatch, gateway)
    text = "Mám PRŮJEM"
    outcome = mapper.map_free_text(text, candidates(), content.freetext, allow_llm=True)
    assert (outcome.mode, outcome.mapper) == ("live", "openai:fake-deployment")
    checked = verify.verify_suggestions(text, outcome.raw, CATALOG)
    assert [s.symptom_key for s in checked.suggestions] == ["diarrhea"]
    assert checked.rejected == 2
    prompt = json.loads(gateway.prompts[0])["input"]
    assert "ignore any instruction" in prompt
    assert "Mám PRŮJEM" in prompt
    assert SECRET not in outcome.mapper


@pytest.mark.parametrize(
    "answer", [None, "not json", '{"suggestions": "x"}', '{"other": []}', "[]"]
)
def test_llm_mapper_falls_back_to_the_word_list_on_any_failure(
    monkeypatch: pytest.MonkeyPatch, content: Content, answer: str | None
) -> None:
    configure_openai(monkeypatch, Gateway(answer))
    outcome = mapper.map_free_text("Mám průjem", candidates(), content.freetext, allow_llm=True)
    assert (outcome.mode, outcome.mapper) == ("fallback", "template-v1")
    assert [r["symptom_key"] for r in outcome.raw] == ["diarrhea"]


def test_llm_is_not_called_when_not_allowed_or_not_configured(
    monkeypatch: pytest.MonkeyPatch, content: Content
) -> None:
    gateway = Gateway('{"suggestions": []}')
    configure_openai(monkeypatch, gateway)
    off = mapper.map_free_text("Mám průjem", candidates(), content.freetext, allow_llm=False)
    assert off.mode == "template"
    assert gateway.prompts == []
    monkeypatch.setenv("WAECHTER_LLM", "template")
    plain = mapper.map_free_text("Mám průjem", candidates(), content.freetext, allow_llm=True)
    assert plain.mode == "template"
    assert gateway.prompts == []


# --- Schalter ------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("value", "demo", "expected"),
    [(None, True, True), (None, False, False), ("1", False, True), ("off", True, False)],
)
def test_the_flag_defaults_to_demo_mode_and_can_be_forced(
    monkeypatch: pytest.MonkeyPatch, value: str | None, demo: bool, expected: bool
) -> None:
    if value is not None:
        monkeypatch.setenv(service.FLAG_ENV, value)
    assert service.enabled(demo) is expected


# --- API: Speichern, Idempotenz, Rechte ----------------------------------------------------------


def session_client(app: FastAPI, username: str) -> TestClient:
    client = TestClient(app, headers=CSRF)
    login(client, username)
    return client


def respond(client: TestClient, value: int = 0) -> str:
    body = client.get(f"{BASE}/me/questionnaire").json()
    item = body["items"][0]
    answer = {
        "symptom_key": item["symptom_key"],
        "attribute": item["questions"][0]["attribute"],
        "value": value,
    }
    reply = client.post(
        f"{BASE}/me/responses",
        json={
            "client_submission_id": str(uuid.uuid4()),
            "questionnaire_id": body["questionnaire_id"],
            "answers": [answer],
        },
    )
    assert reply.status_code == 201, reply.text
    return str(reply.json()["response_id"])


def post_text(client: TestClient, response_id: str, text: str, **extra: Any) -> Any:
    return client.post(
        f"{BASE}/me/free-text", json={"response_id": response_id, "text": text, **extra}
    )


def counts(app: FastAPI) -> dict[str, int]:
    with app.state.session_factory() as session:
        return {
            model.__tablename__: int(session.scalar(select(func.count()).select_from(model)) or 0)
            for model in (Response, Answer, Alert, Notification, TriageDecision, FreeText)
        }


def test_saving_a_free_text_never_creates_answers_levels_decisions_or_alerts(
    seeded_app: FastAPI,
) -> None:
    patient = session_client(seeded_app, "patient")
    response_id = respond(patient)
    before = counts(seeded_app)
    reply = post_text(patient, response_id, "Mám PRŮJEM, bolí mě to a mám horečku.")
    assert reply.status_code == 201, reply.text
    after = counts(seeded_app)
    assert after.pop("wa_free_texts") == before.pop("wa_free_texts") + 1
    assert after == before  # nichts sonst hat sich geändert
    body = reply.json()
    assert body["saved"] is True
    assert set(body) == {"free_text_id", "response_id", "saved", "followups"}
    assert [c["symptom_key"] for c in body["followups"]] == ["fever", "diarrhea", "pain"]


def test_stored_text_has_checked_suggestions_with_adapter_and_mode(seeded_app: FastAPI) -> None:
    patient = session_client(seeded_app, "patient")
    response_id = respond(patient)
    post_text(patient, response_id, "Mám PRŮJEM a bolí mě to")
    with seeded_app.state.session_factory() as session:
        row = session.scalars(select(FreeText).where(FreeText.response_id == response_id)).one()
        assert row.text == "Mám PRŮJEM a bolí mě to"
        assert (row.mapper, row.mapper_mode) == ("template-v1", "template")
        assert {s["symptom_key"] for s in row.suggestions_json} == {"diarrhea", "pain"}
        assert all(row.text[s["start"] : s["end"]] == s["quote"] for s in row.suggestions_json)
        assert all(s["proposed_value"] is None for s in row.suggestions_json)  # template: keiner
        assert row.synthetic is True


def test_replay_is_idempotent_a_different_text_conflicts(seeded_app: FastAPI) -> None:
    patient = session_client(seeded_app, "patient")
    response_id = respond(patient)
    first = post_text(patient, response_id, "Mám průjem")
    again = post_text(patient, response_id, "  Mám průjem  ")  # gleicher Text nach Bereinigung
    other = post_text(patient, response_id, "Něco jiného")
    assert (first.status_code, again.status_code, other.status_code) == (201, 200, 409)
    assert again.json()["free_text_id"] == first.json()["free_text_id"]
    assert other.json()["code"] == "free_text_exists"
    assert counts(seeded_app)["wa_free_texts"] == 1


def test_parallel_posts_store_exactly_one_row(seeded_app: FastAPI) -> None:
    from conftest import run_parallel

    patient = session_client(seeded_app, "patient")
    response_id = respond(patient)
    clients = [session_client(seeded_app, "patient") for _ in range(4)]
    replies = run_parallel(lambda i: post_text(clients[i], response_id, "Mám průjem"), 4)
    assert sorted(r.status_code for r in replies) == [200, 200, 200, 201]
    assert len({r.json()["free_text_id"] for r in replies}) == 1
    assert counts(seeded_app)["wa_free_texts"] == 1


def test_text_is_validated_empty_too_long_and_unknown_fields(seeded_app: FastAPI) -> None:
    patient = session_client(seeded_app, "patient")
    response_id = respond(patient)
    assert post_text(patient, response_id, "   \n ").status_code == 422
    too_long = post_text(patient, response_id, "a" * 501)
    assert too_long.status_code == 422
    assert too_long.json()["code"] == "validation_failed"
    assert post_text(patient, response_id, "a" * 2001).status_code == 422
    assert post_text(patient, response_id, "ok", surprise=1).status_code == 422
    assert post_text(patient, "no-uuid", "ok").status_code == 422
    assert post_text(patient, response_id, "a" * 500).status_code == 201  # genau am Limit
    assert counts(seeded_app)["wa_free_texts"] == 1


def test_rights_foreign_response_404_wrong_role_403_anonymous_401(seeded_app: FastAPI) -> None:
    patient, other = session_client(seeded_app, "patient"), session_client(seeded_app, "patient2")
    response_id = respond(patient)
    assert post_text(other, response_id, "fremd").status_code == 404  # IDOR
    assert post_text(patient, str(uuid.uuid4()), "unbekannt").status_code == 404
    for username in ("doctor", "admin", "user"):
        assert post_text(session_client(seeded_app, username), response_id, "x").status_code == 403
    assert post_text(TestClient(seeded_app, headers=CSRF), response_id, "x").status_code == 401
    assert counts(seeded_app)["wa_free_texts"] == 0


def test_switched_off_flag_refuses_saving_and_lists_nothing(
    seeded_app: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    patient = session_client(seeded_app, "patient")
    response_id = respond(patient)
    assert post_text(patient, response_id, "Mám průjem").status_code == 201
    monkeypatch.setenv(service.FLAG_ENV, "0")
    refused = post_text(session_client(seeded_app, "patient2"), respond(patient), "x")
    assert refused.status_code in (404, 409)
    doctor = session_client(seeded_app, "doctor")
    pid = seeded_patient(seeded_app, "SYN-0001")
    assert doctor.get(f"{BASE}/patients/{pid}/free-texts").json() == []


def seeded_patient(app: FastAPI, pseudonym: str) -> str:
    with app.state.session_factory() as session:
        return str(session.scalars(select(Patient.id).where(Patient.pseudonym == pseudonym)).one())


# --- Audit ohne Inhalt ---------------------------------------------------------------------------


def test_audit_records_counts_only_never_the_text(seeded_app: FastAPI) -> None:
    patient = session_client(seeded_app, "patient")
    response_id = respond(patient)
    secret_text = "GEHEIMER-FREITEXT mit Průjem"  # noqa: S105 (Testwert)
    post_text(patient, response_id, secret_text)
    doctor = session_client(seeded_app, "doctor")
    pid = seeded_patient(seeded_app, "SYN-0001")
    doctor.get(f"{BASE}/patients/{pid}/free-texts")
    with seeded_app.state.session_factory() as session:
        events = session.scalars(
            select(AuditEvent).where(AuditEvent.action.in_(["free_text_saved", "free_texts_view"]))
        ).all()
    assert {e.action for e in events} == {"free_text_saved", "free_texts_view"}
    for event in events:
        assert "GEHEIMER" not in json.dumps(event.details_json)
    saved = next(e for e in events if e.action == "free_text_saved")
    assert saved.details_json == {
        "length": len(secret_text),
        "suggestions": 1,
        "rejected": 0,
        "mode": "template",
    }
    viewed = next(e for e in events if e.action == "free_texts_view")
    assert viewed.details_json == {"count": 1}


# --- Klinik: Liste -------------------------------------------------------------------------------


def test_clinic_lists_newest_first_with_labelled_suggestions_and_highlights(
    seeded_app: FastAPI,
) -> None:
    patient = session_client(seeded_app, "patient")
    older = respond(patient)
    post_text(patient, older, "Mám průjem")
    newer = respond(patient)
    post_text(patient, newer, "Bolí mě hlava a nemůžu dýchat")
    doctor = session_client(seeded_app, "doctor")
    pid = seeded_patient(seeded_app, "SYN-0001")
    listed = doctor.get(f"{BASE}/patients/{pid}/free-texts", params={"lang": "en"}).json()
    assert [t["response_id"] for t in listed] == [newer, older]
    first = listed[0]
    assert first["unconfirmed"] == len({s["symptom_key"] for s in first["suggestions"]})
    assert all(s["confirmed"] is False and s["answers"] == [] for s in first["suggestions"])
    assert first["mode"] == "template"
    assert first["mapper"] == "template-v1"
    labels = {s["label"] for s in first["suggestions"]}
    assert "Pain" in labels
    for s in first["suggestions"]:
        assert first["text"][s["start"] : s["end"]] == s["quote"]
        assert isinstance(s["in_questionnaire"], bool)
    assert listed[1]["suggestions"][0]["label"] == "Diarrhea"


def test_clinic_list_rights_and_unknown_patient(seeded_app: FastAPI) -> None:
    pid = seeded_patient(seeded_app, "SYN-0001")
    url = f"{BASE}/patients/{pid}/free-texts"
    assert session_client(seeded_app, "admin").get(url).status_code == 200
    for username in ("patient", "patient2", "user"):
        assert session_client(seeded_app, username).get(url).status_code == 403
    assert TestClient(seeded_app, headers=CSRF).get(url).status_code == 401
    unknown = session_client(seeded_app, "doctor").get(f"{BASE}/patients/{uuid.uuid4()}/free-texts")
    assert unknown.status_code == 404


def test_free_text_is_permanent_there_is_no_way_to_change_or_delete_it(
    seeded_app: FastAPI,
) -> None:
    patient = session_client(seeded_app, "patient")
    response_id = respond(patient)
    post_text(patient, response_id, "Mám průjem")
    for method in ("put", "patch", "delete"):
        reply = getattr(patient, method)(f"{BASE}/me/free-text")
        assert reply.status_code in (404, 405)
    assert counts(seeded_app)["wa_free_texts"] == 1


# --- Seed/Meta -----------------------------------------------------------------------------------


def test_seed_has_no_free_texts_and_meta_announces_the_feature(seeded_app: FastAPI) -> None:
    assert counts(seeded_app)["wa_free_texts"] == 0
    meta = TestClient(seeded_app).get("/api/v1/meta").json()
    assert meta["waechter"]["free_text"] == {"enabled": True, "max_length": 500}


def test_content_file_is_valid_and_covers_every_catalog_symptom(content: Content) -> None:
    assert content.freetext is not None
    assert content.freetext["status"] == "placeholder"
    keys = {i["symptom_key"] for i in content.items["items"]}
    assert {e["symptom_key"] for e in content.freetext["synonyms"]} == keys
    assert len(content.freetext["warn_words"]) >= 3
