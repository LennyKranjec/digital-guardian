"""HTTP-Schicht des Wächters (dünn): Autorisierung, Parameter, Aufruf des Services."""

import json
from datetime import date, datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response
from pydantic import BaseModel, ConfigDict, Field, StrictInt

from app.api.deps import AdminDep, require_roles
from app.core.clock import ClockDep
from app.core.deps import SessionDep, SettingsDep
from app.core.errors import ApiError
from app.services.auth import Principal
from waechter.constants import ROLE_ADMIN, ROLE_CLINICIAN, ROLE_PATIENT
from waechter.services import acknowledge as acknowledge_service
from waechter.services import advice as advice_service
from waechter.services import (
    alert_queries,
    assessment_queries,
    config_admin,
    fhir_export,
    fhir_push,
    patient_views,
)
from waechter.services import assessments as assessments_service
from waechter.services import checkin as checkin_service
from waechter.services import config as config_service
from waechter.services import enrollment as enrollment_service
from waechter.services import facts as facts_service
from waechter.services import freetext as freetext_service
from waechter.services import medications as medications_service
from waechter.services import questionnaire as questionnaire_service
from waechter.services import responses as responses_service
from waechter.services import summary as summary_service
from waechter.services import triage as triage_service
from waechter.services.subject import own_patient

router = APIRouter(prefix="/waechter", tags=["waechter"])

#: Personal: Ärzt:innen und Administration (falsche Rolle ⇒ 403, anonym ⇒ 401)
StaffDep = Annotated[Principal, Depends(require_roles(ROLE_CLINICIAN, ROLE_ADMIN))]
#: Nur Patient:innen, ausschließlich für `/me/*` (eigene Daten)
PatientDep = Annotated[Principal, Depends(require_roles(ROLE_PATIENT))]

Attribute = Literal["frequency", "severity", "interference", "presence", "amount"]


class ConfigBundle(BaseModel):
    items: dict[str, Any]
    regimens: dict[str, Any]
    ctcae: dict[str, Any]
    rules: dict[str, Any]
    report: dict[str, Any]
    advice: dict[str, Any] | None = None
    medications: dict[str, Any] | None = None
    triage_version: str | None = None


Lang = Annotated[Literal["cs", "en", "de"], Query()]
StatusQuery = Annotated[Literal["open", "acknowledged", "all"], Query()]


class AcknowledgeBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: Literal["contact_patient", "visit_scheduled", "no_action_needed", "other"]
    note: str | None = Field(default=None, max_length=500)


class AssessmentItemBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ctcae_term_id: str = Field(min_length=1, max_length=64)
    grade: StrictInt = Field(ge=0, le=5)
    attribution: Literal["unrelated", "unlikely", "possible", "probable", "definite", "unknown"] = (
        "unknown"
    )
    note: str | None = Field(default=None, max_length=500)


class AssessmentBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    client_submission_id: UUID
    related_alert_ids: list[str] = Field(default_factory=list, max_length=50)
    items: list[AssessmentItemBody] = Field(min_length=1, max_length=100)


class RulesUpdateBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: str = Field(min_length=1, max_length=32)
    rules: dict[str, Any]
    change_note: str | None = Field(default=None, max_length=300)


class ReportUpdateBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: str = Field(min_length=1, max_length=32)
    report: dict[str, Any]
    change_note: str | None = Field(default=None, max_length=300)


class AnswerBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    symptom_key: str = Field(min_length=1, max_length=64)
    attribute: Attribute
    value: StrictInt | None = Field(ge=0, le=4)


class FreeTextBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    response_id: UUID
    text: str = Field(min_length=1, max_length=2000)
    lang: Literal["cs", "en", "de"] | None = None


class FollowupBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    client_submission_id: UUID
    answers: list[AnswerBody] = Field(min_length=1, max_length=40)


class ResponseBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    client_submission_id: UUID
    questionnaire_id: str = Field(min_length=1, max_length=96)
    channel: Literal["web", "phone", "paper"] = "web"
    entered_by: Literal["self", "proxy", "nurse"] = "self"
    answers: list[AnswerBody] = Field(min_length=1, max_length=200)
    recall: Literal["initial_7d", "daily_24h"] | None = None  # T-23: angezeigte Fassung


@router.get("/config")
def get_config(_: StaffDep, session: SessionDep) -> ConfigBundle:
    bundle = ConfigBundle(**config_service.get_bundle(session))
    kb = triage_service.get_kb()
    bundle.triage_version = kb.hash if kb is not None else None
    return bundle


@router.get("/config/triage")
def get_triage_config(_: StaffDep, lang: Lang = "cs") -> dict[str, Any]:
    return triage_service.rule_card(config_service.require_content(), lang)


@router.get("/patients/{patient_id}/triage")
def get_patient_triage(
    patient_id: str,
    principal: StaffDep,
    session: SessionDep,
    clock: ClockDep,
    response_id: Annotated[str | None, Query(max_length=64)] = None,
    lang: Lang = "cs",
) -> dict[str, Any]:
    content = config_service.require_content()
    return triage_service.decision_for_patient(
        session, clock, principal, content, patient_id, response_id, lang
    )


@router.get("/medications")
def search_medications(
    principal: StaffDep,
    session: SessionDep,
    clock: ClockDep,
    q: Annotated[str, Query(min_length=2, max_length=60)],
    lang: Lang = "cs",
) -> list[dict[str, Any]]:
    content = config_service.require_content()
    return medications_service.search_view(session, clock, principal, content, q, lang)


@router.get("/medications/{medication_id}")
def get_medication(
    medication_id: str,
    principal: StaffDep,
    session: SessionDep,
    clock: ClockDep,
    lang: Lang = "cs",
) -> dict[str, Any]:
    content = config_service.require_content()
    return medications_service.detail_view(session, clock, principal, content, medication_id, lang)


@router.get("/me/questionnaire")
def get_my_questionnaire(
    principal: PatientDep,
    session: SessionDep,
    clock: ClockDep,
    lang: Annotated[Literal["cs", "en", "de"] | None, Query()] = None,
) -> dict[str, Any]:
    patient = own_patient(session, principal)
    content = config_service.require_content()
    return questionnaire_service.build_questionnaire(session, patient, content, lang, clock)


class SessionStartBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    client_session_id: UUID
    lang: Literal["cs", "en", "de"] | None = None


class SessionAnswerBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    symptom_key: str = Field(min_length=1, max_length=64)
    attribute: Attribute
    value: StrictInt | None = Field(ge=0, le=4)


@router.post("/me/sessions", status_code=201)
def start_my_session(
    body: SessionStartBody,
    response: Response,
    principal: PatientDep,
    session: SessionDep,
    clock: ClockDep,
) -> dict[str, Any]:
    patient = own_patient(session, principal)
    content = config_service.require_content()
    step, created = checkin_service.start_session(
        session, clock, principal, patient, content, str(body.client_session_id), body.lang
    )
    if not created:
        response.status_code = 200
    return step


@router.get("/me/sessions/{session_id}")
def get_my_session(
    session_id: str, principal: PatientDep, session: SessionDep, clock: ClockDep
) -> dict[str, Any]:
    patient = own_patient(session, principal)
    content = config_service.require_content()
    return checkin_service.get_session(session, clock, principal, patient, content, session_id)


@router.post("/me/sessions/{session_id}/answers")
def answer_my_session(
    session_id: str,
    body: SessionAnswerBody,
    principal: PatientDep,
    session: SessionDep,
    clock: ClockDep,
) -> dict[str, Any]:
    patient = own_patient(session, principal)
    content = config_service.require_content()
    return checkin_service.answer(
        session,
        clock,
        principal,
        patient,
        content,
        session_id,
        body.symptom_key,
        body.attribute,
        body.value,
    )


class SessionUndoBody(BaseModel):
    steps: StrictInt = Field(ge=0, le=200)


@router.post("/me/sessions/{session_id}/undo")
def undo_my_session(
    session_id: str,
    body: SessionUndoBody,
    principal: PatientDep,
    session: SessionDep,
    clock: ClockDep,
) -> dict[str, Any]:
    """T-31: letzte Antwort der offenen Sitzung zurücknehmen (Zurück-Pfeil)."""
    patient = own_patient(session, principal)
    content = config_service.require_content()
    return checkin_service.undo(session, clock, principal, patient, content, session_id, body.steps)


@router.get("/me/advice")
def get_my_advice(
    principal: PatientDep,
    session: SessionDep,
    lang: Annotated[Literal["cs", "en", "de"] | None, Query()] = None,
) -> dict[str, Any]:
    patient = own_patient(session, principal)
    content = config_service.require_content()
    selection = questionnaire_service.select_items(session, patient.id, content)
    return advice_service.help_page(content, selection, lang or patient.language)


@router.post("/me/responses", status_code=201)
def submit_my_response(
    body: ResponseBody,
    response: Response,
    principal: PatientDep,
    session: SessionDep,
    clock: ClockDep,
) -> dict[str, Any]:
    patient = own_patient(session, principal)
    content = config_service.require_content()
    receipt = responses_service.submit(
        session,
        clock,
        principal,
        patient,
        content,
        responses_service.Submission(
            client_submission_id=str(body.client_submission_id),
            questionnaire_id=body.questionnaire_id,
            channel=body.channel,
            entered_by=body.entered_by,
            answers=tuple(
                responses_service.AnswerIn(a.symptom_key, a.attribute, a.value)
                for a in body.answers
            ),
            recall=body.recall,
        ),
    )
    if not receipt.created:
        response.status_code = 200
    return receipt.body()


@router.post("/me/free-text", status_code=201)
def submit_my_free_text(
    body: FreeTextBody,
    response: Response,
    principal: PatientDep,
    session: SessionDep,
    clock: ClockDep,
    settings: SettingsDep,
) -> dict[str, Any]:
    """Freitext zu einer eigenen Antwort (T-22): nur Vorschlag, nie Antwort/Stufe/Meldung."""
    patient = own_patient(session, principal)
    if not freetext_service.enabled(settings.demo_mode):
        raise ApiError(409, "freetext_disabled", "Free text is switched off")
    content = config_service.require_content()
    saved = freetext_service.submit(
        session,
        clock,
        principal,
        patient,
        content,
        response_id=str(body.response_id),
        text=body.text,
        lang=body.lang,
    )
    if not saved.created:
        response.status_code = 200
    return {
        "free_text_id": saved.row.id,
        "response_id": saved.row.response_id,
        "saved": True,
        "followups": freetext_service.cards_of(
            session, saved.row, content, body.lang or saved.row.lang, clock.now()
        ),
    }


@router.get("/me/free-text/followups")
def my_free_text_followups(
    principal: PatientDep,
    session: SessionDep,
    clock: ClockDep,
    settings: SettingsDep,
    lang: Annotated[Literal["cs", "en", "de"] | None, Query()] = None,
) -> list[dict[str, Any]]:
    """Offene Folgefrage-Karten zu den eigenen Freitexten (kritische Symptome zuerst)."""
    patient = own_patient(session, principal)
    if not freetext_service.enabled(settings.demo_mode):
        return []
    content = config_service.require_content()
    return freetext_service.open_cards(session, patient, content, lang, clock.now())


@router.post("/me/free-text/{free_text_id}/answers", status_code=201)
def answer_my_free_text_followups(
    free_text_id: str,
    body: FollowupBody,
    response: Response,
    principal: PatientDep,
    session: SessionDep,
    clock: ClockDep,
    settings: SettingsDep,
) -> dict[str, Any]:
    """Antwort auf Folgefragen: normale Antwort (source free_text_followup) durch Regeln/Triage."""
    patient = own_patient(session, principal)
    if not freetext_service.enabled(settings.demo_mode):
        raise ApiError(409, "freetext_disabled", "Free text is switched off")
    content = config_service.require_content()
    receipt = freetext_service.answer_followups(
        session,
        clock,
        principal,
        patient,
        content,
        free_text_id=free_text_id,
        client_submission_id=str(body.client_submission_id),
        answers=[
            responses_service.AnswerIn(a.symptom_key, a.attribute, a.value) for a in body.answers
        ],
    )
    if not receipt.created:
        response.status_code = 200
    return receipt.body()


@router.get("/patients/{patient_id}/free-texts")
def list_free_texts(
    patient_id: str,
    principal: StaffDep,
    session: SessionDep,
    clock: ClockDep,
    settings: SettingsDep,
    lang: Lang = "cs",
) -> list[dict[str, Any]]:
    """Freitexte der Patientin mit geprüften KI-Vorschlägen (neueste zuerst)."""
    content = config_service.require_content()
    return freetext_service.list_for_patient(
        session,
        clock,
        principal,
        patient_id,
        content,
        lang,
        is_enabled=freetext_service.enabled(settings.demo_mode),
    )


@router.get("/me/responses")
def list_my_responses(principal: PatientDep, session: SessionDep) -> list[dict[str, Any]]:
    return responses_service.list_own(session, own_patient(session, principal))


@router.get("/patients/{patient_id}/alerts")
def list_patient_alerts(
    patient_id: str,
    _: StaffDep,
    session: SessionDep,
    status: StatusQuery = "all",
    lang: Lang = "cs",
) -> list[dict[str, Any]]:
    content = config_service.require_content()
    return alert_queries.list_alerts(session, patient_id, status, content, lang)


@router.get("/alerts/{alert_id}")
def get_alert(alert_id: str, _: StaffDep, session: SessionDep, lang: Lang = "cs") -> dict[str, Any]:
    content = config_service.require_content()
    alert = alert_queries.get_alert(session, alert_id)
    return alert_queries.alert_view(session, alert, content, lang)


@router.post("/alerts/{alert_id}/acknowledge")
def acknowledge_alert(
    alert_id: str,
    body: AcknowledgeBody,
    principal: StaffDep,
    session: SessionDep,
    clock: ClockDep,
    lang: Lang = "cs",
) -> dict[str, Any]:
    content = config_service.require_content()
    return acknowledge_service.acknowledge(
        session, clock, principal, alert_id, body.decision, body.note, content, lang
    )


@router.get("/notifications")
def list_notifications(
    _: StaffDep,
    session: SessionDep,
    lang: Annotated[Literal["cs", "en", "de"] | None, Query()] = None,
) -> list[dict[str, Any]]:
    content = config_service.require_content() if lang is not None else None
    return alert_queries.list_notifications(session, content, lang)


class EnrollmentBody(BaseModel):
    """T-34: neue synthetische Patientin mit Therapie (nur Klinik-Datensatz, kein Konto)."""

    model_config = ConfigDict(extra="forbid")

    diagnosis_code: str | None = Field(default=None, max_length=16)
    regimen_id: str = Field(min_length=1, max_length=64)
    cycle_start: date
    language: Literal["cs", "en", "de"]
    birth_year: StrictInt | None = Field(default=None, ge=1900)
    sex: Literal["female", "male", "other", "unknown"] | None = None
    client_request_id: str | None = Field(default=None, min_length=1, max_length=64)


@router.post("/patients", status_code=201)
def enroll_patient(
    body: EnrollmentBody,
    response: Response,
    principal: StaffDep,
    session: SessionDep,
    clock: ClockDep,
) -> dict[str, str]:
    content = config_service.require_content()
    result = enrollment_service.enroll(
        session,
        clock,
        principal,
        content,
        enrollment_service.Enrollment(**body.model_dump()),
    )
    if not result.created:
        response.status_code = 200
    return result.body()


@router.get("/patients")
def list_patients(
    _: StaffDep, session: SessionDep, clock: ClockDep, settings: SettingsDep, lang: Lang = "cs"
) -> list[dict[str, Any]]:
    content = config_service.require_content()
    rows = patient_views.worklist(session, clock, content, lang)
    if freetext_service.enabled(settings.demo_mode):
        # T-22: Hinweis "Freitext-Zuordnung unbestätigt" (Zahl offener Zuordnungen, kein Alarm)
        open_counts = freetext_service.unconfirmed_counts(
            session, [r["patient_id"] for r in rows], content
        )
        for row in rows:
            # nur bei offenen Zuordnungen: der Vertrag der Arbeitsliste bleibt sonst unverändert
            if open_counts.get(row["patient_id"], 0) > 0:
                row["free_text_unconfirmed"] = open_counts[row["patient_id"]]
    return rows


@router.get("/patients/{patient_id}/overview")
def get_overview(
    patient_id: str,
    principal: StaffDep,
    session: SessionDep,
    clock: ClockDep,
    lang: Lang = "cs",
) -> dict[str, Any]:
    content = config_service.require_content()
    return patient_views.overview(session, clock, principal, patient_id, content, lang)


@router.get("/patients/{patient_id}/timeline")
def get_timeline(
    patient_id: str,
    principal: StaffDep,
    session: SessionDep,
    clock: ClockDep,
    start: Annotated[datetime | None, Query(alias="from")] = None,
    end: Annotated[datetime | None, Query(alias="to")] = None,
    lang: Lang = "cs",
) -> dict[str, Any]:
    content = config_service.require_content()
    return patient_views.timeline(session, clock, principal, patient_id, content, lang, start, end)


@router.get("/patients/{patient_id}/facts/{fact_id}")
def get_fact(
    patient_id: str, fact_id: str, _: StaffDep, session: SessionDep, lang: Lang = "cs"
) -> dict[str, Any]:
    content = config_service.require_content()
    return facts_service.get_fact(session, patient_id, fact_id, content, lang)


@router.get("/patients/{patient_id}/assessment-template")
def get_assessment_template(
    patient_id: str, _: StaffDep, session: SessionDep, clock: ClockDep, lang: Lang = "cs"
) -> dict[str, Any]:
    content = config_service.require_content()
    patient = patient_views.get_patient(session, patient_id)
    return assessments_service.build_template(session, clock, patient, content, lang)


@router.get("/patients/{patient_id}/assessments")
def list_patient_assessments(
    patient_id: str, _: StaffDep, session: SessionDep
) -> list[dict[str, Any]]:
    content = config_service.require_content()
    patient = patient_views.get_patient(session, patient_id)
    return assessment_queries.list_assessments(session, patient.id, content)


@router.post("/patients/{patient_id}/assessments", status_code=201)
def create_patient_assessment(
    patient_id: str,
    body: AssessmentBody,
    response: Response,
    principal: StaffDep,
    session: SessionDep,
    clock: ClockDep,
) -> dict[str, Any]:
    content = config_service.require_content()
    patient = patient_views.get_patient(session, patient_id)
    view, created = assessments_service.create(
        session,
        clock,
        principal,
        patient,
        content,
        str(body.client_submission_id),
        [i.model_dump() for i in body.items],
        body.related_alert_ids,
    )
    if not created:
        response.status_code = 200
    return view


@router.get("/patients/{patient_id}/summary")
def get_summary(patient_id: str, _: StaffDep, session: SessionDep) -> dict[str, Any]:
    patient_views.get_patient(session, patient_id)
    return summary_service.get_latest(session, patient_id)


@router.post("/patients/{patient_id}/summary", status_code=201)
def generate_summary(
    patient_id: str,
    response: Response,
    principal: StaffDep,
    session: SessionDep,
    clock: ClockDep,
    lang: Lang = "cs",
) -> dict[str, Any]:
    content = config_service.require_content()
    patient_views.get_patient(session, patient_id)
    view, created = summary_service.generate(
        session, clock, principal.actor, patient_id, content, lang
    )
    if not created:
        response.status_code = 200
    return view


@router.put("/config/rules")
def update_rules(
    body: RulesUpdateBody,
    principal: AdminDep,
    session: SessionDep,
    clock: ClockDep,
) -> dict[str, Any]:
    return config_admin.update_config(
        session, clock, principal, "rules", body.expected_version, body.rules, body.change_note
    )


@router.put("/config/report")
def update_report(
    body: ReportUpdateBody,
    principal: AdminDep,
    session: SessionDep,
    clock: ClockDep,
) -> dict[str, Any]:
    return config_admin.update_config(
        session, clock, principal, "report", body.expected_version, body.report, body.change_note
    )


@router.get("/config/history")
def get_config_history(
    kind: Annotated[Literal["rules", "report"], Query()],
    _: StaffDep,
    session: SessionDep,
) -> list[dict[str, Any]]:
    return config_admin.history(session, kind)


@router.get("/patients/{patient_id}/fhir")
def export_fhir(
    patient_id: str,
    principal: StaffDep,
    session: SessionDep,
    clock: ClockDep,
    type: Annotated[Literal["collection", "transaction"], Query()] = "collection",
) -> Response:
    """FHIR-R4-Bundle (`collection` oder `transaction`); Content-Type `application/fhir+json`."""
    content = config_service.require_content()
    bundle = fhir_export.export_bundle(session, clock, principal, patient_id, content, type)
    return Response(
        content=json.dumps(bundle, ensure_ascii=False, separators=(",", ":")).encode("utf-8"),
        media_type="application/fhir+json",
    )


@router.post("/patients/{patient_id}/fhir/push")
def push_fhir(
    patient_id: str, principal: AdminDep, session: SessionDep, clock: ClockDep
) -> dict[str, Any]:
    """Transaction-Bundle an den konfigurierten FHIR-Server senden (nur admin)."""
    content = config_service.require_content()
    return fhir_push.push(session, clock, principal, patient_id, content)
