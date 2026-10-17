"""KI-Kurzfassung: Fakten, Prüfung, Dedupe, Provenance, Rechte und Datenschutz (kein Netz)."""

import json
import urllib.error
import uuid
from datetime import timedelta
from email.message import Message
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.main import create_app
from app.persistence.models import AuditEvent
from app.services import seed
from conftest import CHALLENGE_DIR, CSRF, login, make_settings, migrate, run_parallel
from waechter.constants import CONTENT_DIR_ENV
from waechter.llm import adapters
from waechter.llm.facts import build_facts
from waechter.llm.prompt import PROMPT_VERSION
from waechter.models import Answer, Patient, Response, Summary
from waechter.services.summary import _digest

BASE = "/api/v1/waechter"
REAL_CONTENT = CHALLENGE_DIR / "content"


class StepClock:
    """Vom Test vorgestellte Uhr (die neueste Kurzfassung braucht einen späteren Zeitpunkt)."""

    def __init__(self, instant: Any) -> None:
        self.instant = instant

    def now(self) -> Any:
        return self.instant


def staff(app: FastAPI, username: str = "doctor") -> TestClient:
    client = TestClient(app, headers=CSRF)
    login(client, username)
    return client


def pid(app: FastAPI, pseudonym: str) -> str:
    with app.state.session_factory() as session:
        return str(session.scalars(select(Patient.id).where(Patient.pseudonym == pseudonym)).one())


def summaries(app: FastAPI, patient: str) -> list[Summary]:
    with app.state.session_factory() as session:
        return list(session.scalars(select(Summary).where(Summary.patient_id == patient)))


def add_response(app: FastAPI, pseudonym: str, answers: dict[tuple[str, str], int | None]) -> None:
    with app.state.session_factory() as session:
        row = Response(
            patient_id=pid(app, pseudonym),
            client_submission_id=str(uuid.uuid4()),
            channel="web",
            entered_by="self",
            recorded_at=app.state.clock.now(),
            questionnaire_id="items-v1:FIX-REG",
            synthetic=True,
        )
        session.add(row)
        session.flush()
        for (symptom, attribute), value in answers.items():
            session.add(
                Answer(response_id=row.id, symptom_key=symptom, attribute=attribute, value=value)
            )
        session.commit()


# --- Zugriff --------------------------------------------------------------------------------


def test_anonymous_gets_401(seeded_app: FastAPI) -> None:
    anon = TestClient(seeded_app, headers=CSRF)
    p = pid(seeded_app, "SYN-0001")
    assert anon.get(f"{BASE}/patients/{p}/summary").status_code == 401
    assert anon.post(f"{BASE}/patients/{p}/summary").status_code == 401


@pytest.mark.parametrize("username", ["patient", "patient2", "user"])
def test_patients_and_other_roles_get_403(seeded_app: FastAPI, username: str) -> None:
    other = staff(seeded_app, username)
    p = pid(seeded_app, "SYN-0002")
    assert other.get(f"{BASE}/patients/{p}/summary").status_code == 403
    assert other.post(f"{BASE}/patients/{p}/summary").status_code == 403
    assert summaries(seeded_app, p) == []


def test_unknown_patient_is_404(seeded_app: FastAPI) -> None:
    doctor = staff(seeded_app)
    ghost = uuid.uuid4()
    assert doctor.get(f"{BASE}/patients/{ghost}/summary").status_code == 404
    assert doctor.post(f"{BASE}/patients/{ghost}/summary").status_code == 404


def test_get_without_summary_is_404_summary_none(seeded_app: FastAPI) -> None:
    doctor = staff(seeded_app)
    response = doctor.get(f"{BASE}/patients/{pid(seeded_app, 'SYN-0002')}/summary")
    assert response.status_code == 404
    assert response.json()["code"] == "summary_none"


def test_post_needs_csrf_header(seeded_app: FastAPI) -> None:
    doctor = staff(seeded_app)
    bare = TestClient(seeded_app)
    bare.cookies.update(doctor.cookies)
    assert bare.post(f"{BASE}/patients/{pid(seeded_app, 'SYN-0002')}/summary").status_code == 403


# --- Inhalt, Seed, Provenance ---------------------------------------------------------------


def test_demo_patient_has_a_seeded_summary_in_template_mode(seeded_app: FastAPI) -> None:
    doctor = staff(seeded_app)
    p = pid(seeded_app, "SYN-0001")
    summary = doctor.get(f"{BASE}/patients/{p}/summary").json()
    assert summary["mode"] == "fallback"
    assert summary["generator"] == "template-v1"
    assert summary["dropped_sentences"] == 0  # Textbaustein ⇒ 0 unverifizierte Sätze
    assert len(summary["sentences"]) >= 4
    assert all(s["verified"] and s["refs"] for s in summary["sentences"])
    assert summary["disclaimer_key"] == "summary.disclaimer"
    assert summary["provenance_id"].startswith("prov-")
    assert summary["unknown_topics"] == ["assessment"]  # noch keine Arztaufnahme
    assert summary["fact_count"] >= len(summary["sentences"])
    provenance = summary["provenance"]
    assert provenance["mode"] == "fallback"
    assert provenance["requested_mode"] == "template"
    assert provenance["prompt_version"] == PROMPT_VERSION
    assert provenance["model"] is None
    assert len(provenance["facts_hash"]) == 64
    assert summary["generated_at"] == "2026-10-17T09:00:00+02:00"
    overview = doctor.get(f"{BASE}/patients/{p}/overview").json()
    assert overview["summary"] == summary  # Übersicht zeigt die letzte Kurzfassung


def test_every_reference_resolves_to_a_fact_of_the_same_patient(seeded_app: FastAPI) -> None:
    doctor = staff(seeded_app)
    p = pid(seeded_app, "SYN-0001")
    other = pid(seeded_app, "SYN-0002")
    summary = doctor.get(f"{BASE}/patients/{p}/summary").json()
    refs = {r for s in summary["sentences"] for r in s["refs"]}
    assert refs
    for ref in refs:
        assert doctor.get(f"{BASE}/patients/{p}/facts/{ref}").status_code == 200, ref
        assert doctor.get(f"{BASE}/patients/{other}/facts/{ref}").status_code == 404, ref


def test_sentences_cite_the_facts_and_never_state_a_rating(seeded_app: FastAPI) -> None:
    doctor = staff(seeded_app)
    summary = doctor.get(f"{BASE}/patients/{pid(seeded_app, 'SYN-0001')}/summary").json()
    text = " ".join(s["text"] for s in summary["sentences"]).lower()
    assert "r-sev-01" in text  # offene Meldung wird beschrieben, nicht neu bewertet
    for word in ("diagnos", "empfehl", "dosis", "keine sorge", "harmlos"):
        assert word not in text


@pytest.mark.parametrize("pseudonym", ["SYN-0001", "SYN-0002", "SYN-0003", "SYN-0004", "SYN-0005"])
def test_template_mode_yields_no_unverified_sentences_for_every_patient(
    seeded_app: FastAPI, pseudonym: str
) -> None:
    doctor = staff(seeded_app)
    response = doctor.post(f"{BASE}/patients/{pid(seeded_app, pseudonym)}/summary")
    assert response.status_code in (200, 201)
    data = response.json()
    assert data["dropped_sentences"] == 0
    assert data["sentences"]


@pytest.mark.skipif(not REAL_CONTENT.is_dir(), reason="challenge/content/ (A1) nicht vorhanden")
def test_template_mode_is_clean_for_all_real_scenario_patients(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(CONTENT_DIR_ENV, str(REAL_CONTENT))
    settings = make_settings(tmp_path)
    migrate(settings)
    app = create_app(settings)
    with app.state.session_factory() as session:
        seed.provision(session, settings, app.state.registry, app.state.clock)
    doctor = staff(app)
    rows = doctor.get(f"{BASE}/patients").json()
    assert len(rows) >= 5
    for row in rows:
        for lang in ("cs", "en"):
            data = doctor.post(
                f"{BASE}/patients/{row['patient_id']}/summary", params={"lang": lang}
            ).json()
            assert data["dropped_sentences"] == 0, (row["pseudonym"], lang)
            assert data["sentences"], (row["pseudonym"], lang)
            for sentence in data["sentences"]:
                for ref in sentence["refs"]:
                    fact = doctor.get(f"{BASE}/patients/{row['patient_id']}/facts/{ref}")
                    assert fact.status_code == 200, (row["pseudonym"], ref)


# --- Dedupe ---------------------------------------------------------------------------------


def test_same_facts_give_the_same_summary_and_new_facts_a_new_one(seeded_app: FastAPI) -> None:
    doctor = staff(seeded_app)
    p = pid(seeded_app, "SYN-0002")
    url = f"{BASE}/patients/{p}/summary"
    first = doctor.post(url)
    again = doctor.post(url)
    assert (first.status_code, again.status_code) == (201, 200)
    assert again.json() == first.json()  # gleicher Hash ⇒ gleiche summary_id
    assert len(summaries(seeded_app, p)) == 1
    english = doctor.post(url, params={"lang": "en"})
    assert english.status_code == 201
    assert english.json()["summary_id"] != first.json()["summary_id"]
    clock = StepClock(seeded_app.state.clock.now())
    seeded_app.state.clock = clock
    clock.instant += timedelta(hours=1)
    add_response(seeded_app, "SYN-0002", {("nausea", "severity"): 1, ("fever", "presence"): 0})
    changed = doctor.post(url)
    assert changed.status_code == 201
    assert changed.json()["summary_id"] not in {
        first.json()["summary_id"],
        english.json()["summary_id"],
    }
    assert doctor.get(url).json()["summary_id"] == changed.json()["summary_id"]  # GET = letzte


def test_the_requested_mode_is_part_of_the_dedupe_key(
    seeded_app: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    doctor = staff(seeded_app)
    url = f"{BASE}/patients/{pid(seeded_app, 'SYN-0002')}/summary"
    template = doctor.post(url).json()
    monkeypatch.setenv(adapters.ENV_MODE, "cached")  # Cache leer ⇒ Textbaustein, aber anderer Modus
    cached = doctor.post(url)
    assert cached.status_code == 201
    assert cached.json()["summary_id"] != template["summary_id"]
    assert cached.json()["provenance"]["requested_mode"] == "cached"
    assert cached.json()["mode"] == "fallback"


def test_four_parallel_requests_create_exactly_one_summary(seeded_app: FastAPI) -> None:
    p = pid(seeded_app, "SYN-0002")
    doctors = [staff(seeded_app) for _ in range(4)]
    results = run_parallel(lambda i: doctors[i].post(f"{BASE}/patients/{p}/summary"), 4)
    assert sorted(r.status_code for r in results) == [200, 200, 200, 201], [
        (r.status_code, r.text) for r in results
    ]
    assert len({r.json()["summary_id"] for r in results}) == 1
    assert len(summaries(seeded_app, p)) == 1


def test_generation_is_audited_without_text(seeded_app: FastAPI) -> None:
    doctor = staff(seeded_app)
    p = pid(seeded_app, "SYN-0002")
    doctor.post(f"{BASE}/patients/{p}/summary")
    doctor.post(f"{BASE}/patients/{p}/summary")
    with seeded_app.state.session_factory() as session:
        events = list(
            session.scalars(
                select(AuditEvent)
                .where(AuditEvent.action == "generate_summary", AuditEvent.subject_id == p)
                .order_by(AuditEvent.at, AuditEvent.id)
            )
        )
    assert len(events) == 2
    assert {e.actor_role for e in events} == {"clinician"}
    assert {e.details_json["deduplicated"] for e in events} == {True, False}
    for event in events:
        assert set(event.details_json) == {"mode", "sentences", "dropped", "deduplicated"}


# --- Fakten (Datenschutz, Determinismus) ----------------------------------------------------


def test_facts_exclude_names_diagnosis_and_free_text(seeded_app: FastAPI) -> None:
    doctor = staff(seeded_app)
    p = pid(seeded_app, "SYN-0001")
    alert = doctor.get(f"{BASE}/patients/{p}/alerts").json()[0]["alert_id"]
    doctor.post(
        f"{BASE}/alerts/{alert}/acknowledge", json={"decision": "other", "note": "GEHEIM-ACK"}
    )
    doctor.post(
        f"{BASE}/patients/{p}/assessments",
        json={
            "client_submission_id": str(uuid.uuid4()),
            "items": [{"ctcae_term_id": "CTCAE-FIX_NAUSEA", "grade": 2, "note": "GEHEIM-NOTIZ"}],
        },
    )
    from waechter.content import get_content

    content = get_content()
    assert content is not None
    with seeded_app.state.session_factory() as session:
        patient = session.get(Patient, p)
        assert patient is not None
        facts = build_facts(session, seeded_app.state.clock, content, patient, "cs")
    blob = json.dumps([[f.id, f.text] for f in facts.facts], ensure_ascii=False)
    for secret in (
        "GEHEIM-ACK",
        "GEHEIM-NOTIZ",
        "Testpatientin",
        "Synthetische Testdiagnose",
        "SYN-0001",
    ):
        assert secret not in blob
    assert {f.kind for f in facts.facts} >= {
        "therapy",
        "visit",
        "response",
        "alert",
        "observation",
        "assessment",
    }
    assert "assessment" not in facts.unknown_topics


def test_fact_hash_is_stable_and_depends_on_facts_and_language(seeded_app: FastAPI) -> None:
    from waechter.content import get_content

    content = get_content()
    assert content is not None
    p = pid(seeded_app, "SYN-0001")

    def build(lang: str) -> Any:
        with seeded_app.state.session_factory() as session:
            patient = session.get(Patient, p)
            assert patient is not None
            return build_facts(session, seeded_app.state.clock, content, patient, lang)

    assert build("cs").hash == build("cs").hash
    assert build("cs").hash != build("en").hash
    assert build("de").hash == build("de").hash
    assert build("de").hash not in {
        build("cs").hash,
        build("en").hash,
    }  # T-27b: eigene deutsche Texte
    before = build("cs").hash
    add_response(seeded_app, "SYN-0001", {("nausea", "severity"): 0, ("fever", "presence"): 0})
    assert build("cs").hash != before


# --- Adapter im Gesamtablauf (gemockt, kein Netz) -------------------------------------------


def configure_openai(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(adapters.ENV_MODE, "openai")
    monkeypatch.setenv(adapters.ENV_BASE_URL, "https://gateway.invalid/v1")
    monkeypatch.setenv(adapters.ENV_API_KEY, "sk-test-0815")
    monkeypatch.setenv(adapters.ENV_MODEL, "test-model")


class Gateway:
    def __init__(self, text: str | None) -> None:
        self.text = text
        self.requests: list[dict[str, Any]] = []

    def __call__(self, request: Any, timeout: float) -> Any:
        self.requests.append(json.loads(request.data))
        if self.text is None:
            raise urllib.error.HTTPError(request.full_url, 404, "nf", Message(), None)

        class Response:
            def read(self) -> bytes:
                return json.dumps({"output_text": gateway_text}).encode("utf-8")

            def __enter__(self) -> "Response":
                return self

            def __exit__(self, *args: object) -> None:
                return None

        gateway_text = self.text
        return Response()


def test_live_answer_is_verified_sentence_by_sentence(
    seeded_app: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    doctor = staff(seeded_app)
    p = pid(seeded_app, "SYN-0001")
    facts = doctor.get(f"{BASE}/patients/{p}/summary").json()["sentences"]
    ther = next(r for s in facts for r in s["refs"] if r.startswith("ther-"))
    alert = next(r for s in facts for r in s["refs"] if r.startswith("alert-"))
    other_patient_ref = "alert-" + str(uuid.uuid4())
    gateway = Gateway(
        f"Léčba, den cyklu 7 [{ther}]. "  # ok (nur Wörter des Belegs)
        f"Otevřená výstraha [{alert}]. "  # ok (neutrale Meldungswörter)
        f"Nevolnost 9 [{alert}]. "  # falsche Zahl
        f"Wir empfehlen eine Dosisreduktion [{alert}]. "  # Verbotsliste (und Wortprüfung)
        f"Otevřená výstraha [{other_patient_ref}]. "  # erfundener Beleg
        "Alles ist in bester Ordnung."  # ohne Beleg
    )
    add_response(seeded_app, "SYN-0001", {("nausea", "severity"): 2, ("fever", "presence"): 0})
    configure_openai(monkeypatch)
    monkeypatch.setattr(adapters, "_urlopen", gateway)
    response = doctor.post(f"{BASE}/patients/{p}/summary")
    assert response.status_code == 201
    data = response.json()
    assert data["mode"] == "live"
    assert data["generator"] == "openai:test-model"
    assert [s["refs"] for s in data["sentences"]] == [[ther], [alert]]
    assert data["dropped_sentences"] == 4
    assert data["provenance"]["model"] == "test-model"
    assert data["provenance"]["requested_mode"] == "openai"
    # der Prompt enthält nur Fakten-IDs mit Texten, keine Namen, keine Diagnose, keinen Schlüssel
    (request,) = gateway.requests
    prompt = request["input"]
    assert request["store"] is False
    assert f"[{ther}]" in prompt
    assert "[alert-" in prompt
    for secret in ("Testpatientin", "Synthetische Testdiagnose", "SYN-0001", "sk-test-0815"):
        assert secret not in prompt
    with seeded_app.state.session_factory() as session:
        stored = json.dumps(session.scalars(select(Summary.body_json)).all(), ensure_ascii=False)
    assert "sk-test-0815" not in stored


def test_gateway_error_gives_a_clean_template_summary(
    seeded_app: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    doctor = staff(seeded_app)
    configure_openai(monkeypatch)
    monkeypatch.setattr(adapters, "_urlopen", Gateway(None))  # DeploymentNotFound
    response = doctor.post(f"{BASE}/patients/{pid(seeded_app, 'SYN-0002')}/summary")
    assert response.status_code == 201
    data = response.json()
    assert (data["mode"], data["generator"]) == ("fallback", "template-v1")
    assert data["dropped_sentences"] == 0
    assert data["provenance"]["requested_mode"] == "openai"


def test_live_answer_without_any_supported_sentence_falls_back_to_the_template(
    seeded_app: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    """T-07F: bleibt nach der Wortprüfung kein Satz übrig, gilt der Textbaustein (nie leer)."""
    doctor = staff(seeded_app)
    p = pid(seeded_app, "SYN-0001")
    seen = doctor.get(f"{BASE}/patients/{p}/summary").json()["sentences"]
    alert = next(r for s in seen for r in s["refs"] if r.startswith("alert-"))
    configure_openai(monkeypatch)
    monkeypatch.setattr(
        adapters, "_urlopen", Gateway(f"Die Patientin sollte sofort untersucht werden [{alert}].")
    )
    data = doctor.post(f"{BASE}/patients/{p}/summary").json()
    assert (data["mode"], data["generator"]) == ("fallback", "template-v1")
    assert data["sentences"]
    assert data["dropped_sentences"] == 0
    assert data["provenance"]["requested_mode"] == "openai"


def test_two_failed_live_attempts_are_two_attempts_not_one_deduplicated_summary(
    seeded_app: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    doctor = staff(seeded_app)
    url = f"{BASE}/patients/{pid(seeded_app, 'SYN-0002')}/summary"
    configure_openai(monkeypatch)
    monkeypatch.setattr(adapters, "_urlopen", Gateway(None))
    first, second = doctor.post(url), doctor.post(url)
    assert (first.status_code, second.status_code) == (201, 201)
    assert first.json()["summary_id"] != second.json()["summary_id"]


def test_cached_answer_is_used_when_the_key_matches(
    seeded_app: FastAPI, content_copy: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from waechter.content import get_content

    content = get_content()
    assert content is not None
    p = pid(seeded_app, "SYN-0002")
    with seeded_app.state.session_factory() as session:
        patient = session.get(Patient, p)
        assert patient is not None
        facts = build_facts(session, seeded_app.state.clock, content, patient, "cs")
    key = _digest(PROMPT_VERSION, facts.hash)
    ther = next(f.id for f in facts.facts if f.kind == "therapy")
    cache = content_copy / "llm_cache"
    cache.mkdir()
    (cache / f"{key}.json").write_text(
        json.dumps(
            {
                "text": f"Léčba, den cyklu 9 [{ther}]. Nepodložená věta.",
                "model": "rec-model",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv(adapters.ENV_MODE, "cached")
    data = staff(seeded_app).post(f"{BASE}/patients/{p}/summary").json()
    assert (data["mode"], data["generator"]) == ("cached", "cached:rec-model")
    assert [s["refs"] for s in data["sentences"]] == [[ther]]
    assert data["dropped_sentences"] == 1


def test_summaries_are_scoped_per_patient(seeded_app: FastAPI) -> None:
    doctor = staff(seeded_app)
    a, b = pid(seeded_app, "SYN-0001"), pid(seeded_app, "SYN-0002")
    doctor.post(f"{BASE}/patients/{b}/summary")
    first = doctor.get(f"{BASE}/patients/{a}/summary").json()
    second = doctor.get(f"{BASE}/patients/{b}/summary").json()
    assert first["summary_id"] != second["summary_id"]
    with seeded_app.state.session_factory() as session:
        count = session.scalar(
            select(func.count()).select_from(Summary).where(Summary.patient_id == b)
        )
    assert count == 1
