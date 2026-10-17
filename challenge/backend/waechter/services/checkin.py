"""Adaptiver Check-in (Vertrag `triage.md` §3 und §10): Sitzungen unter `/me/sessions`.

Der Zustand einer Sitzung ist allein die geordnete Liste der bisher gestellten Fragen samt Antwort
(`steps_json`); die nächste Frage ist eine reine Funktion davon (Selection Policy, serverseitig und
deterministisch). Eine Antwort gilt nur für die aktuell angebotene Frage (sonst 409
`not_current_question`); die identische Wiederholung der letzten Antwort ist idempotent (offen:
aktueller Stand; beendet: derselbe Beleg, kein neuer Datensatz), eine abweichende Antwort nach dem
Stopp ist 409 `session_closed`. Beim Stopp entsteht über `responses.submit` genau eine gespeicherte
Antwort (Regeln, Triage-Entscheidung, Beleg mit Tipps und Eskalation); der Beleg enthält nie ein
Level.
"""

from typing import Any, Final

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.clock import Clock
from app.core.errors import ApiError, FieldError
from app.services.access import not_found
from app.services.audit import record_audit
from app.services.auth import Principal
from waechter.content import Content
from waechter.models import Answer, CheckinSession, Patient, Response
from waechter.services import responses, triage
from waechter.services.questionnaire import (
    due_for,
    localize,
    max_value,
    options_for,
    question_text,
    reason_for,
    recall_mode,
    select_items,
)
from waechter.timeutil import iso_prague
from waechter.triage.kb import KnowledgeBase
from waechter.triage.policy import FlipPolicy, Question, QuestionKind, Stop
from waechter.triage.runtime import runtime_for

STATUS_OPEN: Final = "open"
STATUS_CLOSED: Final = "closed"
_KIND: Final = {
    QuestionKind.SAFETY: "gate",
    QuestionKind.GATE: "gate",
    QuestionKind.CASCADE: "cascade",
    QuestionKind.ESCALATION: "escalation",
    QuestionKind.ROTATING: "slot",
}


def _invalid(field: str, code: str, message: str) -> ApiError:
    return ApiError(
        422,
        "validation_failed",
        "Invalid answer",
        [FieldError(field=field, code=code, message=message)],
    )


def _own(session: Session, patient: Patient, session_id: str) -> CheckinSession:
    row = session.get(CheckinSession, session_id)
    if row is None or row.patient_id != patient.id:
        raise not_found()  # fremde Sitzung ⇒ 404, nie 403
    return row


def _triple(symptom_key: str, attribute: str, value: int | None) -> list[Any]:
    return [symptom_key, attribute, value]


def _next(
    session: Session, kb: KnowledgeBase, row: CheckinSession, patient_id: str
) -> tuple[Question | Stop, FlipPolicy]:
    runtime = runtime_for(kb, row.profile_id)
    policy = FlipPolicy(runtime.engine)
    previous = triage_previous(session, patient_id, runtime)
    state = {(s, a): v for s, a, v in row.steps_json if v is not None}
    asked = [(s, a) for s, a, _ in row.steps_json]
    return policy.next_question(state, asked, previous, row.cycle_week), policy


def triage_previous(session: Session, patient_id: str, runtime: Any) -> dict[str, int] | None:
    """Symptomgrade des letzten gespeicherten Berichts (Vorbericht für das Trend-Aggregat)."""
    last = session.scalar(
        select(Response)
        .where(Response.patient_id == patient_id)
        .order_by(Response.recorded_at.desc(), Response.id.desc())
        .limit(1)
    )
    if last is None:
        return None
    answers = session.scalars(select(Answer).where(Answer.response_id == last.id)).all()
    profile = runtime.composition.components[0]
    return dict(profile.grades(triage.state_of(answers)))


def _question_view(content: Content, question: Question, lang: str, mode: str) -> dict[str, Any]:
    item = next(i for i in content.items["items"] if i["symptom_key"] == question.symptom_key)
    attribute = next(a for a in item["attributes"] if a["attribute"] == question.attribute)
    return {
        "symptom_key": question.symptom_key,
        "attribute": question.attribute,
        "label": localize(item["label"], lang),
        "text": question_text(attribute, lang, mode),
        "options": options_for(content, question.attribute, lang, question.symptom_key),
        "kind": _KIND[question.kind],
        "safety": question.kind is QuestionKind.SAFETY,
    }


def _finalize(
    session: Session,
    clock: Clock,
    principal: Principal,
    patient: Patient,
    content: Content,
    row: CheckinSession,
    stop: Stop,
) -> None:
    """Speichert die Antwort (einmal, idempotent über die Sitzungs-ID) und schließt die Sitzung."""
    selection = select_items(session, patient.id, content)
    submission = responses.Submission(
        client_submission_id=f"session-{row.id}",
        questionnaire_id=selection.questionnaire_id,
        channel="web",
        entered_by="self",
        answers=tuple(responses.AnswerIn(s, a, v) for s, a, v in row.steps_json),
        lang=row.lang,  # T-36: Beleg/Tipps in der Sprache der Sitzung
    )
    receipt = responses.submit(session, clock, principal, patient, content, submission)
    session.execute(
        update(CheckinSession)
        .where(CheckinSession.id == row.id, CheckinSession.status == STATUS_OPEN)
        .values(
            status=STATUS_CLOSED,
            response_id=receipt.response_id,
            stop_reason=stop.reason,
            stop_incomplete=stop.incomplete,
            version=CheckinSession.version + 1,
        )
    )
    session.commit()
    session.refresh(row)


def _advance(
    session: Session,
    clock: Clock,
    principal: Principal,
    patient: Patient,
    content: Content,
    kb: KnowledgeBase,
    row: CheckinSession,
) -> Question | None:
    """Nächste Frage; bei Stopp wird die Sitzung abgeschlossen (dann `None`)."""
    if row.status == STATUS_CLOSED:
        return None
    result, _ = _next(session, kb, row, patient.id)
    if isinstance(result, Stop):
        _finalize(session, clock, principal, patient, content, row, result)
        return None
    return result


def _receipt_body(session: Session, row: CheckinSession) -> dict[str, Any] | None:
    response = session.get(Response, row.response_id) if row.response_id else None
    if response is None:
        return None
    if response.receipt_json is not None:
        return dict(response.receipt_json)
    return None


def _view(
    session: Session,
    clock: Clock,
    content: Content,
    kb: KnowledgeBase,
    patient: Patient,
    row: CheckinSession,
    question: Question | None,
) -> dict[str, Any]:
    profile = kb.profile(row.profile_id)
    selection = select_items(session, patient.id, content)
    body: dict[str, Any] = {
        "session_id": row.id,
        "progress": {"asked": len(row.steps_json), "max": profile.max_questions},
        "selection_reason": reason_for(selection, row.lang),
        "next": _question_view(
            content, question, row.lang, recall_mode(session, patient.id, clock.now())
        )
        if question is not None
        else None,
        "stop": None,
        "receipt": None,
    }
    if row.status == STATUS_CLOSED:
        body["stop"] = {"reason": row.stop_reason, "incomplete": bool(row.stop_incomplete)}
        body["receipt"] = _receipt_body(session, row)
    due = due_for(session, patient.id, content, clock.now())
    if due is not None:
        body["due"] = {
            "next_due_at": iso_prague(due.next_due_at),
            "overdue": due.overdue,
            "interval_days": due.interval_days,
        }
    return body


def _require_kb(content: Content) -> KnowledgeBase:
    kb = triage.get_kb(content)
    if kb is None:
        raise ApiError(409, "triage_unavailable", "Adaptive check-in is not available")
    return kb


def start_session(
    session: Session,
    clock: Clock,
    principal: Principal,
    patient: Patient,
    content: Content,
    client_session_id: str,
    lang: str | None,
) -> tuple[dict[str, Any], bool]:
    """Sitzung starten oder die Sitzung derselben `client_session_id` fortsetzen (`created`)."""
    kb = _require_kb(content)
    existing = session.scalar(
        select(CheckinSession).where(
            CheckinSession.patient_id == patient.id,
            CheckinSession.client_session_id == client_session_id,
        )
    )
    created = False
    if existing is None:
        profile_id = triage.profile_id_for(kb, session, patient.id)
        if profile_id is None:
            raise ApiError(409, "triage_unavailable", "No triage profile for the current therapy")
        now = clock.now()
        existing = CheckinSession(
            patient_id=patient.id,
            client_session_id=client_session_id,
            lang=lang or patient.language,
            profile_id=profile_id,
            cycle_week=triage.cycle_week(session, patient.id, now),
            steps_json=[],
            status=STATUS_OPEN,
            version=1,
            created_at=now,
            synthetic=True,
        )
        try:
            session.add(existing)
            session.flush()
            record_audit(
                session,
                clock,
                principal.actor,
                "start_session",
                "session",
                target_id=existing.id,
                subject_id=patient.id,
            )
            session.commit()
            created = True
        except IntegrityError:  # paralleler Start mit derselben ID: dessen Sitzung gilt
            session.rollback()
            existing = session.scalars(
                select(CheckinSession).where(
                    CheckinSession.patient_id == patient.id,
                    CheckinSession.client_session_id == client_session_id,
                )
            ).one()
    question = _advance(session, clock, principal, patient, content, kb, existing)
    return _view(session, clock, content, kb, patient, existing, question), created


def get_session(
    session: Session,
    clock: Clock,
    principal: Principal,
    patient: Patient,
    content: Content,
    session_id: str,
) -> dict[str, Any]:
    """Aktueller Stand der eigenen Sitzung (offen: nächste Frage; beendet: Stopp und Beleg)."""
    kb = _require_kb(content)
    row = _own(session, patient, session_id)
    question = _advance(session, clock, principal, patient, content, kb, row)
    return _view(session, clock, content, kb, patient, row, question)


def answer(
    session: Session,
    clock: Clock,
    principal: Principal,
    patient: Patient,
    content: Content,
    session_id: str,
    symptom_key: str,
    attribute: str,
    value: int | None,
) -> dict[str, Any]:
    """Antwort auf die angebotene Frage; liefert die nächste Frage oder den Stopp mit Beleg."""
    kb = _require_kb(content)
    row = _own(session, patient, session_id)
    triple = _triple(symptom_key, attribute, value)
    if row.status == STATUS_CLOSED:
        if row.steps_json and list(row.steps_json[-1]) == triple:
            return _view(
                session, clock, content, kb, patient, row, None
            )  # identisch ⇒ gleicher Beleg
        raise ApiError(409, "session_closed", "The session is already closed")
    profile = kb.profile(row.profile_id)
    item = profile.items.get(symptom_key)
    if item is None or attribute not in item.attributes:
        raise _invalid("symptom_key", "unknown_item", "Item not in questionnaire")
    if value is not None and not 0 <= value <= max_value(attribute):
        raise _invalid("value", "out_of_range", "Value out of range")
    current, _ = _next(session, kb, row, patient.id)
    if isinstance(current, Stop):
        _finalize(session, clock, principal, patient, content, row, current)
        if row.steps_json and list(row.steps_json[-1]) == triple:
            return _view(session, clock, content, kb, patient, row, None)
        raise ApiError(409, "session_closed", "The session is already closed")
    if (current.symptom_key, current.attribute) != (symptom_key, attribute):
        if (
            row.steps_json and list(row.steps_json[-1]) == triple
        ):  # Wiederholung der letzten Antwort
            return _view(session, clock, content, kb, patient, row, current)
        raise ApiError(409, "not_current_question", "Only the offered question can be answered")
    updated = session.execute(
        update(CheckinSession)
        .where(
            CheckinSession.id == row.id,
            CheckinSession.version == row.version,
            CheckinSession.status == STATUS_OPEN,
        )
        .values(steps_json=[*row.steps_json, triple], version=row.version + 1)
    )
    if updated.rowcount != 1:  # type: ignore[attr-defined]  # paralleler Request war schneller
        session.rollback()
        session.refresh(row)
        if row.steps_json and list(row.steps_json[-1]) == triple:
            question = _advance(session, clock, principal, patient, content, kb, row)
            return _view(session, clock, content, kb, patient, row, question)
        raise ApiError(409, "not_current_question", "Only the offered question can be answered")
    session.commit()
    session.refresh(row)
    question = _advance(session, clock, principal, patient, content, kb, row)
    return _view(session, clock, content, kb, patient, row, question)


def undo(
    session: Session,
    clock: Clock,
    principal: Principal,
    patient: Patient,
    content: Content,
    session_id: str,
    steps: int,
) -> dict[str, Any]:
    """T-31: nimmt die letzte Antwort einer OFFENEN Sitzung zurück und bietet ihre Frage erneut an.

    `steps` = Anzahl der Antworten, die der Client sieht (Idempotenz): stimmt sie nicht mehr (schon
    zurückgenommen, parallele Anfrage), wird nur der aktuelle Stand geliefert. Eine beendete Sitzung
    (Beleg erstellt) kann nicht zurückgenommen werden ⇒ 409 `session_closed`. Die Policy ist
    deterministisch über die Antworten; die nächste Frage ist danach die zurückgenommene.
    """
    kb = _require_kb(content)
    row = _own(session, patient, session_id)
    if row.status == STATUS_CLOSED:
        raise ApiError(409, "session_closed", "The session is already closed")
    if steps < 1 or len(row.steps_json) != steps:
        question = _advance(session, clock, principal, patient, content, kb, row)
        return _view(session, clock, content, kb, patient, row, question)
    updated = session.execute(
        update(CheckinSession)
        .where(
            CheckinSession.id == row.id,
            CheckinSession.version == row.version,
            CheckinSession.status == STATUS_OPEN,
        )
        .values(steps_json=list(row.steps_json[:-1]), version=row.version + 1)
    )
    if updated.rowcount != 1:  # type: ignore[attr-defined]  # paralleler Request war schneller
        session.rollback()
    else:
        session.commit()
    session.refresh(row)
    if row.status == STATUS_CLOSED:
        raise ApiError(409, "session_closed", "The session is already closed")
    question = _advance(session, clock, principal, patient, content, kb, row)
    return _view(session, clock, content, kb, patient, row, question)
