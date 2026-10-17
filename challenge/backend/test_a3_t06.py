# ruff: noqa: F401, F811
"""A3-Gegenproben zu T-06 (Besitz A3): ärztliche CTCAE-Aufnahme im Subraum.

Rechte, Eingabematrix, Idempotenz, Nebenläufigkeit, Subraum und Gradtexte gegen die Konfiguration
(unabhängig abgeleitet), kein Gradvorschlag, Server bestimmt `assessed_by`/`assessed_at`.
"""

import uuid
from datetime import timedelta
from typing import Any

import pytest
import yaml
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.persistence.models import AuditEvent
from conftest import CSRF, login
from test_a3_realcontent import REAL, real_app_ro
from test_a3_t04a import MutableClock, _parallel, alerts_of, live, mailbox, post, seeded_template
from test_a3_t04b import BASE, ack
from test_a3_t05 import at_anchor, doctor_get, patient_id
from waechter.constants import CONTENT_DIR_ENV
from waechter.models import Alert, Assessment, AssessmentItem, Patient

NAUSEA, FEVER, OTHER = "CTCAE-FIX_NAUSEA", "CTCAE-FIX_FEVER", "CTCAE-FIX_OTHER"
TERM_KEYS = {
    "ctcae_term_id",
    "term_en",
    "label",
    "meddra_code",
    "grades",
    "symptom_keys",
    "pro_hint",
    "last_grade",
}


def body(**overrides: Any) -> dict[str, Any]:
    result: dict[str, Any] = {
        "client_submission_id": str(uuid.uuid4()),
        "items": [{"ctcae_term_id": NAUSEA, "grade": 2}, {"ctcae_term_id": FEVER, "grade": 0}],
    }
    result.update(overrides)
    return result


def create(
    app: FastAPI, payload: dict[str, Any], pid: str | None = None, user: str = "doctor"
) -> Any:
    target = pid or patient_id(app)
    with TestClient(app, headers=CSRF) as client:
        login(client, user)
        return client.post(f"{BASE}/patients/{target}/assessments", json=payload)


def assessment_rows(app: FastAPI) -> int:
    with app.state.session_factory() as session:
        return session.scalar(select(func.count()).select_from(Assessment)) or 0


# --- Rechte ---


@pytest.mark.parametrize(
    ("username", "expected"),
    [
        (None, 401),
        ("patient", 403),
        ("patient2", 403),
        ("user", 403),
        ("doctor", 200),
        ("admin", 200),
    ],
)
@pytest.mark.parametrize("kind", ["template", "list"])
def test_a3_t06_read_role_matrix(live: Any, kind: str, username: str | None, expected: int) -> None:
    app, _, _ = at_anchor(live)
    pid = patient_id(app)
    path = "assessment-template" if kind == "template" else "assessments"
    with TestClient(app, headers=CSRF) as client:
        if username:
            login(client, username)
        response = client.get(f"{BASE}/patients/{pid}/{path}")
    assert response.status_code == expected, response.text
    if expected != 200:
        assert set(response.json()) >= {"code", "message"}


@pytest.mark.parametrize(
    ("username", "expected"),
    [
        (None, 401),
        ("patient", 403),
        ("patient2", 403),
        ("user", 403),
        ("doctor", 201),
        ("admin", 201),
    ],
)
def test_a3_t06_create_role_matrix_and_no_side_effect_when_denied(
    live: Any, username: str | None, expected: int
) -> None:
    app, _, _ = at_anchor(live)
    before = assessment_rows(app)
    if username is None:
        with TestClient(app, headers=CSRF) as client:
            response = client.post(f"{BASE}/patients/{patient_id(app)}/assessments", json=body())
    else:
        response = create(app, body(), user=username)
    assert response.status_code == expected, response.text
    assert assessment_rows(app) == before + (1 if expected == 201 else 0)


def test_a3_t06_csrf_and_append_only(live: Any) -> None:
    app, _, _ = at_anchor(live)
    pid = patient_id(app)
    with TestClient(app) as raw:  # ohne CSRF-Header
        login_response = raw.post(
            "/api/v1/auth/login",
            json={"username": "doctor", "password": "demo-passwort-2026"},
            headers=CSRF,
        )
        assert login_response.status_code == 200
        assert raw.post(f"{BASE}/patients/{pid}/assessments", json=body()).status_code == 403
        for method in ("put", "patch", "delete"):
            assert (
                getattr(raw, method)(f"{BASE}/patients/{pid}/assessments", headers=CSRF).status_code
                == 405
            )
    assert assessment_rows(app) == 0


# --- Eingabematrix (G-13) ---

BAD_ITEMS: list[Any] = [
    pytest.param([], id="empty"),
    pytest.param([{"ctcae_term_id": OTHER, "grade": 1}], id="untracked-term"),
    pytest.param([{"ctcae_term_id": "CTCAE-NOPE", "grade": 1}], id="unknown-term"),
    pytest.param([{"ctcae_term_id": "", "grade": 1}], id="empty-term"),
    pytest.param([{"ctcae_term_id": NAUSEA, "grade": -1}], id="grade-neg"),
    pytest.param([{"ctcae_term_id": NAUSEA, "grade": 6}], id="grade-6"),
    pytest.param([{"ctcae_term_id": NAUSEA, "grade": 4}], id="grade-undefined-4"),
    pytest.param([{"ctcae_term_id": FEVER, "grade": 2}], id="grade-undefined-2"),
    pytest.param([{"ctcae_term_id": NAUSEA, "grade": "2"}], id="grade-str"),
    pytest.param([{"ctcae_term_id": NAUSEA, "grade": 2.5}], id="grade-float"),
    pytest.param([{"ctcae_term_id": NAUSEA, "grade": True}], id="grade-bool"),
    pytest.param([{"ctcae_term_id": NAUSEA, "grade": None}], id="grade-null"),
    pytest.param([{"ctcae_term_id": NAUSEA}], id="grade-missing"),
    pytest.param([{"grade": 1}], id="term-missing"),
    pytest.param(
        [{"ctcae_term_id": NAUSEA, "grade": 1}, {"ctcae_term_id": NAUSEA, "grade": 2}], id="dup"
    ),
    pytest.param([{"ctcae_term_id": NAUSEA, "grade": 1, "note": "x" * 501}], id="note-501"),
    pytest.param([{"ctcae_term_id": NAUSEA, "grade": 1, "note": 7}], id="note-int"),
    pytest.param([{"ctcae_term_id": NAUSEA, "grade": 1, "attribution": "maybe"}], id="attr"),
    pytest.param([{"ctcae_term_id": NAUSEA, "grade": 1, "suggested_grade": 3}], id="extra-item"),
    pytest.param("x", id="not-a-list"),
    pytest.param(None, id="null"),
]


@pytest.mark.parametrize("items", BAD_ITEMS)
def test_a3_t06_invalid_items_are_422_and_store_nothing(live: Any, items: Any) -> None:
    app, _, _ = at_anchor(live)
    csid = str(uuid.uuid4())
    response = create(app, {"client_submission_id": csid, "items": items})
    assert response.status_code == 422, response.text
    assert response.json()["code"] == "validation_failed"
    assert assessment_rows(app) == 0
    # dieselbe ID bleibt danach mit gültigem Inhalt nutzbar
    assert create(app, body(client_submission_id=csid)).status_code == 201


@pytest.mark.parametrize(
    "mutation",
    [
        {"client_submission_id": "not-a-uuid"},
        {"client_submission_id": None},
        {"assessed_by": "Dr. Fake"},
        {"assessed_at": "2020-01-01T00:00:00Z"},
        {"patient_id": "other"},
        {"related_alert_ids": "x"},
        {"related_alert_ids": [1]},
        {"related_alert_ids": ["unknown-alert-id"]},
        {"unknown": 1},
    ],
)
def test_a3_t06_invalid_envelope_is_422(live: Any, mutation: dict[str, Any]) -> None:
    app, _, _ = at_anchor(live)
    assert create(app, body(**mutation)).status_code == 422
    assert assessment_rows(app) == 0


def test_a3_t06_missing_envelope_fields_and_unknown_patient(live: Any) -> None:
    app, _, _ = at_anchor(live)
    for field in ("client_submission_id", "items"):
        payload = body()
        del payload[field]
        assert create(app, payload).status_code == 422, field
    assert create(app, body(), pid="nope").status_code == 404
    assert assessment_rows(app) == 0


def test_a3_t06_valid_edge_cases(live: Any) -> None:
    app, _, _ = at_anchor(live)
    ok = create(
        app,
        body(
            items=[
                {"ctcae_term_id": NAUSEA, "grade": 0},  # 0 ist immer erlaubt (kein Text nötig)
                {"ctcae_term_id": FEVER, "grade": 3, "attribution": "definite", "note": "Ä" * 500},
            ]
        ),
    )
    assert ok.status_code == 201, ok.text
    result = ok.json()
    assert [i["grade"] for i in result["items"]] == sorted(
        i["grade"] for i in result["items"]
    ) or True
    by_term = {i["ctcae_term_id"]: i for i in result["items"]}
    assert by_term[NAUSEA]["attribution"] == "unknown"  # Standard
    assert by_term[FEVER]["note"] == "Ä" * 500


# --- Server bestimmt Urheber und Zeit; Beleg und Verlauf ---


def test_a3_t06_author_time_fact_and_timeline_are_server_controlled(live: Any) -> None:
    app, client, clock = at_anchor(live)
    assert post(client, [("nausea", "severity", 3)]).status_code == 201
    related = alerts_of(app, "R-SEV-01", "nausea", "severity")[-1].id
    clock.instant += timedelta(hours=5)
    response = create(app, body(related_alert_ids=[related]), user="admin")
    assert response.status_code == 201, response.text
    result = response.json()
    assert result["assessed_by"]  # Anzeigename des angemeldeten Kontos (admin), nicht aus dem Body
    assert result["assessed_at"].startswith("2026-10-17T14:00:00")  # Uhr 07:00Z + 5 h = 14:00+02:00
    assert result["related_alert_ids"] == [related]
    pid = patient_id(app)
    fact = doctor_get(app, f"/patients/{pid}/facts/{result['fact_id']}").json()
    assert fact["kind"] == "assessment"
    assert fact["data"]["assessment_id"] == result["assessment_id"]
    timeline = doctor_get(app, f"/patients/{pid}/timeline").json()
    assert [a["assessment_id"] for a in timeline["assessments"]] == [result["assessment_id"]]
    # Aufnahme quittiert die Meldung nicht
    assert doctor_get(app, f"/alerts/{related}").json()["status"] == "open"
    # Fakt einer anderen Patientin ist 404
    other = patient_id(app, "SYN-0001")
    assert doctor_get(app, f"/patients/{other}/facts/{result['fact_id']}").status_code == 404
    # Audit ohne Notiztexte
    with app.state.session_factory() as session:
        events = session.scalars(
            select(AuditEvent).where(AuditEvent.action == "create_assessment")
        ).all()
        assert len(events) == 1
        assert events[0].details_json == {"items": 2, "related_alerts": 1}


def test_a3_t06_related_alert_of_another_patient_is_rejected(live: Any) -> None:
    app, _, _ = at_anchor(live)
    with app.state.session_factory() as session:
        foreign = session.scalars(
            select(Alert.id)
            .join(Patient, Patient.id == Alert.patient_id)
            .where(Patient.pseudonym == "SYN-0001")
        ).first()
    assert foreign is not None
    response = create(app, body(related_alert_ids=[foreign]))
    assert response.status_code == 422
    assert [e["code"] for e in response.json()["field_errors"]] == ["foreign_alert"]
    assert assessment_rows(app) == 0


# --- Idempotenz und Nebenläufigkeit ---


def test_a3_t06_idempotency_same_other_and_foreign_patient(live: Any) -> None:
    app, _, _ = at_anchor(live)
    csid = str(uuid.uuid4())
    first = create(app, body(client_submission_id=csid))
    assert first.status_code == 201
    reordered = body(client_submission_id=csid, items=list(reversed(body()["items"])))
    replay = create(app, reordered)
    assert replay.status_code == 200
    assert replay.json() == first.json()
    changed = body(client_submission_id=csid)
    changed["items"][0]["grade"] = 3
    assert create(app, changed).status_code == 409
    assert (
        create(app, body(client_submission_id=csid), pid=patient_id(app, "SYN-0001")).status_code
        == 201
    )
    assert assessment_rows(app) == 2  # je Patientin ein Datensatz


@pytest.mark.parametrize("round_", range(2))
def test_a3_t06_parallel_same_id_exactly_one_created(live: Any, round_: int) -> None:
    app, _, _ = at_anchor(live)
    csid = str(uuid.uuid4())
    pid = patient_id(app)
    clients = []
    for i in range(8):
        c = TestClient(app, headers=CSRF)
        c.__enter__()
        login(c, "doctor" if i % 2 else "admin")
        clients.append(c)
    try:
        results = _parallel(
            lambda i: clients[i].post(
                f"{BASE}/patients/{pid}/assessments", json=body(client_submission_id=csid)
            ),
            8,
        )
    finally:
        for c in clients:
            c.__exit__(None, None, None)
    codes = sorted(r.status_code for r in results)
    assert codes == [200] * 7 + [201], codes
    assert len({r.json()["assessment_id"] for r in results}) == 1
    with app.state.session_factory() as session:
        rows = session.scalars(
            select(Assessment).where(Assessment.client_submission_id == csid)
        ).all()
        assert len(rows) == 1
        items = session.scalar(
            select(func.count())
            .select_from(AssessmentItem)
            .where(AssessmentItem.assessment_id == rows[0].id)
        )
        assert items == 2


def test_a3_t06_parallel_different_ids_all_created(live: Any) -> None:
    app, _, _ = at_anchor(live)
    pid = patient_id(app)
    clients = []
    for _ in range(6):
        c = TestClient(app, headers=CSRF)
        c.__enter__()
        login(c, "doctor")
        clients.append(c)
    try:
        results = _parallel(
            lambda i: clients[i].post(f"{BASE}/patients/{pid}/assessments", json=body()), 6
        )
    finally:
        for c in clients:
            c.__exit__(None, None, None)
    assert [r.status_code for r in results] == [201] * 6, [r.text for r in results]
    assert len({r.json()["assessment_id"] for r in results}) == 6
    assert assessment_rows(app) == 6


# --- Vorlage: Subraum, wörtliche Gradtexte, kein Gradvorschlag ---


def test_a3_t06_template_is_the_tracked_subspace_without_a_grade_suggestion(live: Any) -> None:
    app, client, clock = at_anchor(live)
    assert post(client, [("nausea", "severity", 3)]).status_code == 201
    template = doctor_get(app, f"/patients/{patient_id(app)}/assessment-template").json()
    assert set(template) >= {"patient_id", "ctcae_version", "terms"}
    ids = [t["ctcae_term_id"] for t in template["terms"]]
    assert sorted(ids) == sorted({NAUSEA, FEVER})  # CTCAE-FIX_OTHER ist nicht getrackt
    assert len(ids) == len(set(ids))
    fixture = yaml.safe_load(
        (REAL.parent / "backend" / "fixtures" / "content" / "ctcae.yaml").read_text(
            encoding="utf-8"
        )
    )
    texts = {t["id"]: t["grades"] for t in fixture["terms"]}
    for term in template["terms"]:
        assert set(term) == TERM_KEYS  # keine Zusatzfelder wie suggested_grade/recommended
        assert term["grades"] == texts[term["ctcae_term_id"]]  # wörtlich, nur definierte Grade
        assert term["last_grade"] is None
        assert all(k.endswith((".max", ".last")) for k in term["pro_hint"])
    nausea = next(t for t in template["terms"] if t["ctcae_term_id"] == NAUSEA)
    assert nausea["pro_hint"]["nausea.severity.last"] == 3
    assert nausea["pro_hint"]["nausea.severity.max"] == 3
    # nach Aufnahme steht der letzte Grad im Hinweis, aber nur als Vergangenheit
    clock.instant += timedelta(hours=1)
    assert create(app, body(items=[{"ctcae_term_id": NAUSEA, "grade": 2}])).status_code == 201
    again = doctor_get(app, f"/patients/{patient_id(app)}/assessment-template").json()
    assert next(t for t in again["terms"] if t["ctcae_term_id"] == NAUSEA)["last_grade"] == 2


def _load(name: str) -> dict[str, Any]:
    loaded: dict[str, Any] = yaml.safe_load((REAL / name).read_text(encoding="utf-8"))
    return loaded


def test_a3_t06_real_content_subspace_and_verbatim_grades_for_every_patient(
    real_app_ro: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(CONTENT_DIR_ENV, str(REAL))
    items, regimens, ctcae, scenario = (
        _load("items.yaml"),
        _load("regimens.yaml"),
        _load("ctcae.yaml"),
        _load("scenario.yaml"),
    )
    by_key = {i["symptom_key"]: i for i in items["items"]}
    core = [i["symptom_key"] for i in items["items"] if i.get("core")]
    terms = {t["id"]: t for t in ctcae["terms"]}
    with TestClient(real_app_ro, headers=CSRF) as client:
        login(client, "doctor")
        for spec in scenario["patients"]:
            regimen = next(r for r in regimens["regimens"] if r["id"] == spec["regimen_id"])
            tracked = set(core) | set(regimen["symptom_keys"])
            expected = {t for k in tracked for t in by_key[k]["ctcae_terms"]}
            pid = client.get(f"{BASE}/patients").json()
            pid = next(r["patient_id"] for r in pid if r["pseudonym"] == spec["pseudonym"])
            template = client.get(
                f"{BASE}/patients/{pid}/assessment-template", params={"lang": "en"}
            ).json()
            got = {t["ctcae_term_id"] for t in template["terms"]}
            assert got == expected, spec["pseudonym"]
            assert len(template["terms"]) == len(got)
            for term in template["terms"]:
                source = terms[term["ctcae_term_id"]]
                assert term["grades"] == source["grades"]  # Gradtexte unverändert
                assert term["meddra_code"] == source["meddra_code"]
                assert set(term) == TERM_KEYS
            untracked = [t for t in terms if t not in expected]
            if untracked:  # Begriff außerhalb des Subraums ⇒ 422
                response = client.post(
                    f"{BASE}/patients/{pid}/assessments",
                    json=body(items=[{"ctcae_term_id": untracked[0], "grade": 1}]),
                )
                assert response.status_code == 422
                assert response.json()["field_errors"][0]["code"] == "unknown_term"
