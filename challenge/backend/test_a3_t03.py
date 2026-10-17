"""A3-Gegenproben zu T-03 (Besitz A3): IDOR patient/patient2, Paralleltests, Eingabematrix, Zeit.

Mutationsgeprüft (docs/verification/T-03.md). Keine Tagesdaten, keine Seed-Zahlen.
"""

import logging
import threading
import uuid
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.main import create_app
from app.persistence.models import AuditEvent
from conftest import CSRF, login, make_settings, migrate
from waechter.models import Answer, Patient, Response
from waechter.services import hooks
from waechter.services.questionnaire import max_value

QUESTIONNAIRE = "/api/v1/waechter/me/questionnaire"
RESPONSES = "/api/v1/waechter/me/responses"
QID = "items-v1:FIX-REG"
RECEIPT_KEYS = {"response_id", "recorded_at", "answered", "skipped", "message_key"}
FORBIDDEN_KEYS = {"level", "alert", "alerts", "traffic_light", "grade", "rule_id", "flag", "status"}


def _parallel[T](action: Callable[[int], T], workers: int) -> list[T]:
    """Wie `run_parallel` (tests/backend/helpers.py), von hier aus nicht importierbar."""
    barrier = threading.Barrier(workers)

    def task(index: int) -> T:
        barrier.wait(timeout=10)
        return action(index)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(task, i) for i in range(workers)]
        return [f.result(timeout=60) for f in futures]


def payload(csid: str | None = None, severity: int = 2, **overrides: Any) -> dict[str, Any]:
    result: dict[str, Any] = {
        "client_submission_id": csid or str(uuid.uuid4()),
        "questionnaire_id": QID,
        "answers": [
            {"symptom_key": "nausea", "attribute": "severity", "value": severity},
            {"symptom_key": "fever", "attribute": "presence", "value": 0},
        ],
    }
    result.update(overrides)
    return result


def session_client(app: FastAPI, username: str) -> TestClient:
    test_client = TestClient(app, headers=CSRF)
    test_client.__enter__()
    login(test_client, username)
    return test_client


@pytest.fixture
def two_patients(seeded_app: FastAPI) -> Any:
    first, second = session_client(seeded_app, "patient"), session_client(seeded_app, "patient2")
    yield first, second
    first.__exit__(None, None, None)
    second.__exit__(None, None, None)


def rows(app: FastAPI, csid: str) -> list[Response]:
    with app.state.session_factory() as session:
        return list(session.scalars(select(Response).where(Response.client_submission_id == csid)))


# --- Konten und Rollen ------------------------------------------------------------------------


def test_a3_two_patient_accounts_resolve_to_two_different_patients(
    seeded_app: FastAPI, two_patients: Any
) -> None:
    first, second = two_patients
    me1 = first.get("/api/v1/auth/me").json()
    me2 = second.get("/api/v1/auth/me").json()
    assert me1["role"] == me2["role"] == "patient"
    assert me1["subject_id"]
    assert me2["subject_id"]
    assert me1["subject_id"] != me2["subject_id"]
    with seeded_app.state.session_factory() as session:
        names = {p.id: p.pseudonym for p in session.scalars(select(Patient))}
    assert names[me1["subject_id"]] == "SYN-0001"
    assert names[me2["subject_id"]] == "SYN-0002"
    assert first.get(QUESTIONNAIRE).json()["lang"] == "cs"  # Sprache der Patientin (G-18)
    assert second.get(QUESTIONNAIRE).json()["lang"] == "en"


@pytest.mark.parametrize(
    ("username", "expected"),
    [
        (None, 401),
        ("patient", 200),
        ("patient2", 200),
        ("doctor", 403),
        ("admin", 403),
        ("user", 403),
    ],
)
@pytest.mark.parametrize("path", [QUESTIONNAIRE, RESPONSES])
def test_a3_me_get_role_matrix(
    seeded_app: FastAPI, path: str, username: str | None, expected: int
) -> None:
    with TestClient(seeded_app, headers=CSRF) as test_client:
        if username:
            login(test_client, username)
        response = test_client.get(path)
    assert response.status_code == expected, response.text
    if expected != 200:
        assert set(response.json()) >= {"code", "message"}


@pytest.mark.parametrize(
    ("username", "expected"),
    [(None, 401), ("doctor", 403), ("admin", 403), ("user", 403)],
)
def test_a3_me_post_denied_for_everyone_but_patients(
    seeded_app: FastAPI, username: str | None, expected: int
) -> None:
    csid = str(uuid.uuid4())
    with TestClient(seeded_app, headers=CSRF) as test_client:
        if username:
            login(test_client, username)
        assert test_client.post(RESPONSES, json=payload(csid)).status_code == expected
    assert rows(seeded_app, csid) == []  # nichts gespeichert


# --- IDOR patient ↔ patient2 -------------------------------------------------------------------


def test_a3_patient_cannot_see_or_touch_the_other_patients_data(
    seeded_app: FastAPI, two_patients: Any
) -> None:
    first, second = two_patients
    csid = str(uuid.uuid4())
    created = first.post(RESPONSES, json=payload(csid, severity=3))
    assert created.status_code == 201
    receipt = created.json()
    assert set(receipt) == RECEIPT_KEYS
    # (1) Liste der anderen enthält nichts Fremdes
    seen = second.get(RESPONSES).json()
    assert receipt["response_id"] not in {r["response_id"] for r in seen}
    # (2) Abfrage-Parameter und Header werden ignoriert (keine Subjektumschaltung)
    pid = first.get("/api/v1/auth/me").json()["subject_id"]
    for extra in ({"patient_id": pid}, {"subject_id": pid}, {"patientId": pid}):
        listing = second.get(RESPONSES, params=extra).json()
        assert receipt["response_id"] not in {r["response_id"] for r in listing}
    spoofed = second.get(RESPONSES, headers={"X-Patient-Id": pid, "X-Subject-Id": pid}).json()
    assert receipt["response_id"] not in {r["response_id"] for r in spoofed}
    # (3) Body-Feld patient_id wird abgelehnt, nichts gespeichert
    spoof_csid = str(uuid.uuid4())
    spoof = second.post(RESPONSES, json=payload(spoof_csid, patient_id=pid))
    assert spoof.status_code == 422
    assert rows(seeded_app, spoof_csid) == []
    # (4) F-02 (A0-Entscheid): Idempotenzschlüssel gilt je Patientin. Dieselbe ID bei B ist eine
    #     eigene Sendung (201), nie der Beleg von A; der Replay danach liefert B's eigenen Beleg.
    clash = second.post(RESPONSES, json=payload(csid, severity=3))
    assert clash.status_code == 201, clash.text
    assert clash.json()["response_id"] != receipt["response_id"]
    assert receipt["response_id"] not in clash.text
    assert pid not in clash.text
    own_replay = second.post(RESPONSES, json=payload(csid.upper(), severity=3))
    assert own_replay.status_code == 200
    assert own_replay.json() == clash.json()
    # (5) Besitzerin A ist unverändert: ihre Zeile, ihr Beleg
    stored = [r for r in rows(seeded_app, csid) if r.patient_id == pid]
    assert len(stored) == 1
    assert len(rows(seeded_app, csid)) == 2  # eine Zeile je Patientin
    other_body = first.post(RESPONSES, json=payload(csid, severity=4))
    assert other_body.status_code == 409  # eigene ID, anderer Inhalt (G-10)
    assert other_body.json()["code"] == "idempotency_conflict"
    replay = first.post(RESPONSES, json=payload(csid, severity=3))
    assert replay.status_code == 200
    assert replay.json() == receipt
    # (6) die andere Patientin kann dieselbe Sendung unter eigener ID speichern (kein Zustandsleck)
    assert second.post(RESPONSES, json=payload(str(uuid.uuid4()), severity=3)).status_code == 201


def test_a3_foreign_id_does_not_block_or_alter_the_owner(
    seeded_app: FastAPI, two_patients: Any
) -> None:
    """B 'verbrennt' die ID von A nicht: A's Replay und A's Liste bleiben unverändert."""
    first, second = two_patients
    csid = str(uuid.uuid4())
    receipt = first.post(RESPONSES, json=payload(csid)).json()
    before = first.get(RESPONSES).json()
    # F-02: B's Sendung mit derselben ID ist eine eigene Sendung und ändert A nicht
    assert second.post(RESPONSES, json=payload(csid, severity=4)).status_code == 201
    assert first.get(RESPONSES).json() == before
    assert first.post(RESPONSES, json=payload(csid)).json() == receipt


# --- Paralleltests (Mutations- und Stresslauf) --------------------------------------------------


def test_a3_eight_identical_submissions_one_created_seven_replays(seeded_app: FastAPI) -> None:
    csid = str(uuid.uuid4())
    clients = [session_client(seeded_app, "patient") for _ in range(8)]
    try:
        results = _parallel(lambda i: clients[i].post(RESPONSES, json=payload(csid, severity=3)), 8)
    finally:
        for c in clients:
            c.__exit__(None, None, None)
    codes = sorted(r.status_code for r in results)
    assert codes == [200] * 7 + [201], codes
    assert len({r.json()["response_id"] for r in results}) == 1
    assert len({str(r.json()) for r in results}) == 1  # identische Belege
    with seeded_app.state.session_factory() as audit_session:
        events = audit_session.scalars(
            select(AuditEvent).where(AuditEvent.target_id == results[0].json()["response_id"])
        ).all()
        assert len(events) == 1  # Replays erzeugen kein weiteres Audit
        assert events[0].details_json == {"answered": 2, "skipped": 0}
    with seeded_app.state.session_factory() as session:
        ids = [r.id for r in rows(seeded_app, csid)]
        assert len(ids) == 1
        assert (
            session.scalar(
                select(func.count()).select_from(Answer).where(Answer.response_id.in_(ids))
            )
            == 2
        )


def test_a3_eight_different_ids_all_succeed_without_server_errors(seeded_app: FastAPI) -> None:
    csids = [str(uuid.uuid4()) for _ in range(8)]
    clients = [session_client(seeded_app, "patient") for _ in range(8)]
    try:
        results = _parallel(lambda i: clients[i].post(RESPONSES, json=payload(csids[i])), 8)
    finally:
        for c in clients:
            c.__exit__(None, None, None)
    assert [r.status_code for r in results] == [201] * 8, [r.text for r in results]
    assert len({r.json()["response_id"] for r in results}) == 8
    assert all(len(rows(seeded_app, c)) == 1 for c in csids)


@pytest.mark.parametrize("round_", range(3))
def test_a3_same_id_from_two_patients_one_record_each(seeded_app: FastAPI, round_: int) -> None:
    csid = str(uuid.uuid4())
    clients = [session_client(seeded_app, "patient") for _ in range(3)] + [
        session_client(seeded_app, "patient2") for _ in range(3)
    ]
    try:
        results = _parallel(lambda i: clients[i].post(RESPONSES, json=payload(csid)), 6)
    finally:
        for c in clients:
            c.__exit__(None, None, None)
    codes = [r.status_code for r in results]
    assert set(codes) <= {200, 201}, codes  # nie 5xx, nie 409 (F-02: Schlüssel je Patientin)
    # je Patientin genau ein Datensatz: pro Gruppe genau einmal 201 und zweimal 200
    assert sorted(codes[:3]) == [200, 200, 201], codes
    assert sorted(codes[3:]) == [200, 200, 201], codes
    stored = rows(seeded_app, csid)
    assert len(stored) == 2
    owners = {r.patient_id for r in stored}
    assert owners == {
        clients[0].get("/api/v1/auth/me").json()["subject_id"],
        clients[3].get("/api/v1/auth/me").json()["subject_id"],
    }


def test_a3_two_patients_in_parallel_do_not_mix_up_data(seeded_app: FastAPI) -> None:
    first = [session_client(seeded_app, "patient") for _ in range(4)]
    second = [session_client(seeded_app, "patient2") for _ in range(4)]
    clients = first + second
    csids = [str(uuid.uuid4()) for _ in range(8)]
    try:
        results = _parallel(
            lambda i: clients[i].post(RESPONSES, json=payload(csids[i], severity=i % 5)), 8
        )
        assert [r.status_code for r in results] == [201] * 8
        pid1 = first[0].get("/api/v1/auth/me").json()["subject_id"]
        pid2 = second[0].get("/api/v1/auth/me").json()["subject_id"]
        for i, csid in enumerate(csids):
            (stored,) = rows(seeded_app, csid)
            assert stored.patient_id == (pid1 if i < 4 else pid2)
        mine = {r["response_id"] for r in first[0].get(RESPONSES).json()}
        theirs = {r["response_id"] for r in second[0].get(RESPONSES).json()}
        assert not mine & theirs
    finally:
        for c in clients:
            c.__exit__(None, None, None)


# --- Eingabematrix (G-10) ---------------------------------------------------------------------

BAD_ANSWERS = [
    pytest.param([{"symptom_key": "nausea", "attribute": "severity", "value": -1}], id="neg"),
    pytest.param([{"symptom_key": "nausea", "attribute": "severity", "value": 5}], id="gt4"),
    pytest.param([{"symptom_key": "nausea", "attribute": "severity", "value": "2"}], id="str"),
    pytest.param([{"symptom_key": "nausea", "attribute": "severity", "value": 2.5}], id="float"),
    pytest.param([{"symptom_key": "nausea", "attribute": "severity", "value": True}], id="bool"),
    pytest.param([{"symptom_key": "nausea", "attribute": "severity"}], id="no-value"),
    pytest.param([{"symptom_key": "fever", "attribute": "presence", "value": 2}], id="presence2"),
    pytest.param([{"symptom_key": "fever", "attribute": "presence", "value": 4}], id="presence4"),
    pytest.param([{"symptom_key": "nausea", "attribute": "nope", "value": 1}], id="attr"),
    pytest.param([{"symptom_key": "nausea", "attribute": "amount", "value": 1}], id="not-asked"),
    pytest.param([{"symptom_key": "nope", "attribute": "severity", "value": 1}], id="symptom"),
    pytest.param([{"symptom_key": "", "attribute": "severity", "value": 1}], id="empty-key"),
    pytest.param(
        [
            {"symptom_key": "nausea", "attribute": "severity", "value": 1},
            {"symptom_key": "nausea", "attribute": "severity", "value": 2},
        ],
        id="dup",
    ),
    pytest.param([], id="empty"),
    pytest.param(
        [{"symptom_key": "nausea", "attribute": "severity", "value": 1, "extra": 1}], id="extra"
    ),
    pytest.param("x", id="not-a-list"),
    pytest.param(None, id="null-list"),
]


@pytest.mark.parametrize("answers", BAD_ANSWERS)
def test_a3_invalid_answers_are_422_and_leave_no_trace(
    seeded_app: FastAPI, two_patients: Any, answers: Any
) -> None:
    first, _ = two_patients
    csid = str(uuid.uuid4())
    before = len(first.get(RESPONSES).json())
    response = first.post(RESPONSES, json=payload(csid, answers=answers))
    assert response.status_code == 422, response.text
    assert response.json()["code"] in {"validation_failed", "validation_error"}
    assert rows(seeded_app, csid) == []
    assert len(first.get(RESPONSES).json()) == before
    # Antwort, die dieselbe ID danach mit gültigem Inhalt nutzt, wird normal gespeichert
    assert first.post(RESPONSES, json=payload(csid)).status_code == 201


@pytest.mark.parametrize(
    "mutation",
    [
        {"client_submission_id": "not-a-uuid"},
        {"client_submission_id": None},
        {"client_submission_id": 12345},
        {"questionnaire_id": "items-v1:OTHER"},
        {"questionnaire_id": ""},
        {"channel": "fax"},
        {"entered_by": "robot"},
        {"unknown_field": 1},
    ],
)
def test_a3_invalid_envelope_is_422(two_patients: Any, mutation: dict[str, Any]) -> None:
    first, _ = two_patients
    assert first.post(RESPONSES, json=payload(**mutation)).status_code == 422


def test_a3_missing_envelope_fields_are_422(two_patients: Any) -> None:
    first, _ = two_patients
    for field in ("client_submission_id", "questionnaire_id", "answers"):
        body = payload()
        del body[field]
        assert first.post(RESPONSES, json=body).status_code == 422, field
    assert (
        first.post(
            RESPONSES, content=b"{not json", headers={"Content-Type": "application/json"}
        ).status_code
        == 422
    )
    assert first.post(RESPONSES, json=[1, 2]).status_code == 422


def test_a3_valid_edge_submissions(seeded_app: FastAPI, two_patients: Any) -> None:
    first, _ = two_patients
    # alles übersprungen: erlaubt, zählt als 0 beantwortet
    csid = str(uuid.uuid4())
    skipped = first.post(
        RESPONSES,
        json=payload(
            csid,
            answers=[
                {"symptom_key": "nausea", "attribute": "severity", "value": None},
                {"symptom_key": "fever", "attribute": "presence", "value": None},
            ],
        ),
    )
    assert skipped.status_code == 201
    assert (skipped.json()["answered"], skipped.json()["skipped"]) == (0, 2)
    with seeded_app.state.session_factory() as session:
        (stored,) = rows(seeded_app, csid)
        values = session.scalars(select(Answer.value).where(Answer.response_id == stored.id)).all()
        assert values == [None, None]  # nie imputiert (nicht 0)
    # Teilantwort: nur ein Item; Grenzwerte 0 und 4; presence 0/1
    for answers in (
        [{"symptom_key": "nausea", "attribute": "severity", "value": 0}],
        [{"symptom_key": "nausea", "attribute": "severity", "value": 4}],
        [{"symptom_key": "fever", "attribute": "presence", "value": 1}],
    ):
        assert first.post(RESPONSES, json=payload(answers=answers)).status_code == 201
    # UUID in Großschreibung und ohne Bindestriche gelten als dieselbe ID (Replay, kein Duplikat)
    base = uuid.uuid4()
    one = first.post(RESPONSES, json=payload(str(base)))
    assert one.status_code == 201
    for form in (str(base).upper(), base.hex):
        again = first.post(RESPONSES, json=payload(form))
        assert again.status_code == 200, form
        assert again.json() == one.json(), form
    assert len(rows(seeded_app, str(base))) == 1


def test_a3_receipt_and_list_never_contain_ratings(two_patients: Any) -> None:
    first, _ = two_patients
    receipt = first.post(RESPONSES, json=payload(severity=4)).json()  # höchster Wert, kein Alarm
    assert set(receipt) == RECEIPT_KEYS
    assert receipt["message_key"] == "patient.response.saved"
    for entry in first.get(RESPONSES).json():
        assert set(entry) == {"response_id", "recorded_at", "channel", "entered_by", "answers"}
    flat = str(receipt) + str(first.get(RESPONSES).json())
    for word in FORBIDDEN_KEYS:
        assert f"'{word}'" not in flat, word


def test_a3_validation_errors_and_logs_do_not_echo_input(
    two_patients: Any, caplog: pytest.LogCaptureFixture
) -> None:
    first, _ = two_patients
    marker = "A3-ECHO-MARKER-5521"
    caplog.set_level(logging.DEBUG)
    bodies = [
        payload(answers=[{"symptom_key": marker, "attribute": "severity", "value": 1}]),
        payload(answers=[{"symptom_key": "nausea", "attribute": "severity", "value": marker}]),
        payload(questionnaire_id=marker),
    ]
    for body in bodies:
        response = first.post(RESPONSES, json=body)
        assert response.status_code == 422
        assert marker not in response.text.replace(f".{marker}", "")  # Feldpfad ja, Wert nie
    if marker in caplog.text:  # nur als Teil eines Feldpfads erlaubt, nie als Wert
        assert caplog.text.count(marker) == caplog.text.count(f".{marker}")


# --- Fragebogen --------------------------------------------------------------------------------


def test_a3_options_match_server_side_limits(two_patients: Any) -> None:
    """Jede angebotene Option muss der Server auch annehmen (sonst 422 für gültige Auswahl)."""
    first, _ = two_patients
    questionnaire = first.get(QUESTIONNAIRE).json()
    for item in questionnaire["items"]:
        for question in item["questions"]:
            values = [o["value"] for o in question["options"]]
            assert values == list(range(max_value(question["attribute"]) + 1)), question
            assert all(o["label"] for o in question["options"])


def test_a3_every_offered_option_is_accepted(seeded_app: FastAPI, two_patients: Any) -> None:
    first, _ = two_patients
    questionnaire = first.get(QUESTIONNAIRE).json()
    answers = [
        {"symptom_key": i["symptom_key"], "attribute": q["attribute"], "value": o["value"]}
        for i in questionnaire["items"]
        for q in i["questions"]
        for o in q["options"]
    ]
    # je Wert eine eigene Sendung (Duplikate je Sendung sind verboten)
    by_round: dict[int, list[dict[str, Any]]] = {}
    for position, a in enumerate(answers):
        by_round.setdefault(
            sum(
                1
                for b in answers[:position]
                if b["symptom_key"] == a["symptom_key"] and b["attribute"] == a["attribute"]
            ),
            [],
        ).append(a)
    for part in by_round.values():
        response = first.post(
            RESPONSES,
            json=payload(questionnaire_id=questionnaire["questionnaire_id"], answers=part),
        )
        assert response.status_code == 201, response.text


def test_a3_questionnaire_language_fallback_and_validation(two_patients: Any) -> None:
    first, second = two_patients
    de = first.get(QUESTIONNAIRE, params={"lang": "de"}).json()
    en = first.get(QUESTIONNAIRE, params={"lang": "en"}).json()
    assert de["lang"] == "de"
    assert de["selection_reason"].startswith("Fragen")
    assert all(q["text"] for i in de["items"] for q in i["questions"])  # nie leer (Fallback)
    # v1.9: <items>:<regime>:<gruppe|none>; die alte ID (QID) bleibt für Antworten zulässig
    assert de["questionnaire_id"] == en["questionnaire_id"] == f"{QID}:none"
    for bad in ("fr", "", "CS", "cs,en"):
        assert first.get(QUESTIONNAIRE, params={"lang": bad}).status_code == 422, bad
    assert second.get(QUESTIONNAIRE).json()["recall_period"]


def test_a3_questionnaire_is_read_only_and_identical_for_repeated_calls(two_patients: Any) -> None:
    first, _ = two_patients
    a, b = first.get(QUESTIONNAIRE).json(), first.get(QUESTIONNAIRE).json()
    assert a == b
    assert first.post(QUESTIONNAIRE, json={}).status_code == 405
    assert first.delete(RESPONSES).status_code == 405


# --- Zeit (Europe/Prague, G-04) ---------------------------------------------------------------


@pytest.mark.parametrize(
    ("instant", "suffix"),
    [
        (datetime(2026, 10, 25, 0, 59, 59, tzinfo=UTC), "+02:00"),  # 1 s vor Umstellung
        (datetime(2026, 10, 25, 1, 0, 0, tzinfo=UTC), "+01:00"),  # Umstellung
        (datetime(2026, 3, 29, 0, 59, 59, tzinfo=UTC), "+01:00"),
        (datetime(2026, 3, 29, 1, 0, 0, tzinfo=UTC), "+02:00"),
        (datetime(2026, 12, 31, 23, 30, tzinfo=UTC), "+01:00"),
    ],
)
def test_a3_receipt_time_follows_prague_dst(tmp_path: Path, instant: datetime, suffix: str) -> None:
    settings = make_settings(tmp_path).model_copy(update={"app_frozen_now": instant})
    migrate(settings)
    app = create_app(settings)
    try:
        with app.state.session_factory() as session:
            from app.services import seed

            seed.provision(session, settings, app.state.registry, app.state.clock)
            session.commit()
        with TestClient(app, headers=CSRF) as test_client:
            login(test_client, "patient")
            receipt = test_client.post(RESPONSES, json=payload()).json()
            listed = next(
                r
                for r in test_client.get(RESPONSES).json()
                if r["response_id"] == receipt["response_id"]
            )
    finally:
        app.state.engine.dispose()
    stamp = datetime.fromisoformat(receipt["recorded_at"])
    assert receipt["recorded_at"].endswith(suffix), receipt["recorded_at"]
    assert stamp.astimezone(UTC) == instant  # derselbe Zeitpunkt, nur andere Schreibweise
    assert listed["recorded_at"] == receipt["recorded_at"]


def test_a3_same_instant_submissions_have_stable_order(two_patients: Any) -> None:
    """Eingefrorene Uhr: gleiche recorded_at ⇒ Reihenfolge deterministisch (recorded_at, id)."""
    first, _ = two_patients
    ids = [first.post(RESPONSES, json=payload(severity=i)).json()["response_id"] for i in range(3)]
    listing = [r["response_id"] for r in first.get(RESPONSES).json()]
    assert listing == [r["response_id"] for r in first.get(RESPONSES).json()]
    new = [i for i in listing if i in ids]
    # gleiche Zeit ⇒ zuletzt eingefügt zuerst (T-22: `rowid` statt zufälliger UUID; SQLite)
    assert new == list(reversed(ids))
    times = [r["recorded_at"] for r in first.get(RESPONSES).json()]
    assert times == sorted(times, reverse=True)  # neueste zuerst


# --- Hook / Datenverlust ---------------------------------------------------------------------


def test_a3_hook_failure_must_not_lose_the_patients_answers(
    seeded_app: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(session: Any, response: Any) -> None:
        raise RuntimeError("Regelauswertung kaputt")

    monkeypatch.setattr(hooks, "on_response_saved", boom)
    csid = str(uuid.uuid4())
    with TestClient(seeded_app, headers=CSRF, raise_server_exceptions=False) as test_client:
        login(test_client, "patient")
        test_client.post(RESPONSES, json=payload(csid))
    assert len(rows(seeded_app, csid)) == 1  # die Eingabe der Patientin bleibt erhalten


def test_a3_all_422_of_one_endpoint_share_one_error_code(two_patients: Any) -> None:
    first, _ = two_patients
    shape = first.post(RESPONSES, json=payload(client_submission_id="not-a-uuid"))
    domain = first.post(
        RESPONSES,
        json=payload(answers=[{"symptom_key": "nope", "attribute": "severity", "value": 1}]),
    )
    assert shape.status_code == domain.status_code == 422
    assert shape.json()["code"] == domain.json()["code"]


@pytest.mark.parametrize(("day_offset", "hour"), [(8, None), (10, 9), (30, 8)])
def test_a3_seed_times_keep_the_prague_local_hour_across_dst(
    day_offset: int, hour: int | None
) -> None:
    from waechter.services.seed import shift
    from waechter.timeutil import to_prague

    anchor = datetime.fromisoformat("2026-10-17T09:00:00+02:00")
    local = to_prague(shift(anchor, day_offset, hour))
    assert local.hour == (hour if hour is not None else 9)
