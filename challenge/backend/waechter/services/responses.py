"""Antworten der Patientin: validieren, idempotent speichern, auditieren, auflisten.

Idempotenz (Schlüssel je Patientin): dieselbe `client_submission_id` mit gleichem Inhalt ⇒
gleicher Beleg (200), mit anderem Inhalt ⇒ 409 `idempotency_conflict`. Die Eindeutigkeit
sichert der Unique-Index in der DB, nicht nur eine Vorabprüfung (Paralleltest).
Übersprungenes (`null`) bleibt fehlend, wird nie imputiert.
Die Antwort an die Patientin enthält nie Ampel, Meldung oder Grad.
"""

import logging
from dataclasses import dataclass, field, replace
from typing import Any, Final, Literal

from sqlalchemy import literal_column, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.clock import Clock
from app.core.errors import ApiError, FieldError
from app.services.audit import record_audit
from app.services.auth import Principal
from waechter.content import Content
from waechter.models import Answer, Patient, Response
from waechter.services import advice, evaluation
from waechter.services.questionnaire import (
    Selection,
    max_value,
    recall_mode,
    select_items,
    wording_for,
)
from waechter.timeutil import iso_prague

logger = logging.getLogger("waechter.responses")

CONFIRMATION_KEY: Final = "patient.response.saved"
SOURCE_QUESTIONNAIRE: Final = "questionnaire"
#: Antwort auf eine Folgefrage zu einem Freitext (T-22): Karte aus dem GESAMTEN Katalog
SOURCE_FOLLOWUP: Final = "free_text_followup"
Channel = Literal["web", "phone", "paper"]
EnteredBy = Literal["self", "proxy", "nurse"]


@dataclass(frozen=True)
class AnswerIn:
    symptom_key: str
    attribute: str
    value: int | None


@dataclass(frozen=True)
class Submission:
    client_submission_id: str
    questionnaire_id: str
    channel: Channel
    entered_by: EnteredBy
    answers: tuple[AnswerIn, ...]
    #: `questionnaire` (Check-in) oder `free_text_followup` (Folgefrage, Katalog statt Fragebogen)
    source: str = SOURCE_QUESTIONNAIRE
    free_text_id: str | None = None
    lang: str | None = None
    recall: str | None = None  # T-23: angezeigte Variante (initial_7d | daily_24h), sonst berechnet


@dataclass(frozen=True)
class Receipt:
    response_id: str
    recorded_at: str
    answered: int
    skipped: int
    message_key: str
    created: bool
    #: v1.9: `advice[]` und `escalation` (leer, wenn es keine advice.yaml gibt)
    extras: dict[str, Any] = field(default_factory=dict)

    def body(self) -> dict[str, Any]:
        return {
            **self.extras,
            "response_id": self.response_id,
            "recorded_at": self.recorded_at,
            "answered": self.answered,
            "skipped": self.skipped,
            "message_key": self.message_key,
        }


def _invalid(field: str, code: str, message: str) -> FieldError:
    return FieldError(field=field, code=code, message=message)


def validate(
    submission: Submission, selection: Selection, catalog: set[tuple[str, str]] | None = None
) -> None:
    """422 mit Feldpfaden (nie Werten), wenn die Sendung nicht zum Fragebogen passt.

    Folgefragen (`free_text_followup`) dürfen jedes Symptom des Katalogs betreffen (`catalog`),
    nicht nur die Items des Fragebogens der Patientin.
    """
    errors: list[FieldError] = []
    followup = submission.source == SOURCE_FOLLOWUP and catalog is not None
    if not followup and submission.questionnaire_id not in selection.accepted_ids:
        errors.append(_invalid("questionnaire_id", "mismatch", "Questionnaire does not match"))
    allowed = catalog if followup and catalog is not None else selection.allowed_pairs()
    seen: set[tuple[str, str]] = set()
    for index, answer in enumerate(submission.answers):
        field = f"answers.{index}"
        pair = (answer.symptom_key, answer.attribute)
        if pair not in allowed:
            errors.append(
                _invalid(f"{field}.symptom_key", "unknown_item", "Item not in questionnaire")
            )
        elif pair in seen:
            errors.append(_invalid(f"{field}.symptom_key", "duplicate_item", "Duplicate item"))
        elif answer.value is not None and answer.value > max_value(answer.attribute):
            errors.append(_invalid(f"{field}.value", "out_of_range", "Value out of range"))
        seen.add(pair)
    if errors:
        raise ApiError(422, "validation_failed", "Invalid submission", errors)


def _stored_answers(session: Session, response_id: str) -> dict[tuple[str, str], int | None]:
    rows = session.scalars(select(Answer).where(Answer.response_id == response_id)).all()
    return {(a.symptom_key, a.attribute): a.value for a in rows}


def _receipt(session: Session, response: Response, *, created: bool) -> Receipt:
    answers = _stored_answers(session, response.id)
    answered = sum(1 for v in answers.values() if v is not None)
    return Receipt(
        response_id=response.id,
        recorded_at=iso_prague(response.recorded_at),
        answered=answered,
        skipped=len(answers) - answered,
        message_key=CONFIRMATION_KEY,
        created=created,
    )


def _same_content(session: Session, existing: Response, submission: Submission) -> bool:
    return (
        existing.questionnaire_id == submission.questionnaire_id
        and existing.channel == submission.channel
        and existing.entered_by == submission.entered_by
        and _stored_answers(session, existing.id)
        == {(a.symptom_key, a.attribute): a.value for a in submission.answers}
    )


def _replay(
    session: Session, patient: Patient, submission: Submission, content: Content
) -> Receipt | None:
    """Beleg einer schon gespeicherten Sendung; `None`, wenn die ID neu ist; 409 bei Abweichung."""
    existing = session.scalar(
        select(Response).where(
            Response.patient_id == patient.id,
            Response.client_submission_id == submission.client_submission_id,
        )
    )
    if existing is None:
        return None
    if not _same_content(session, existing, submission):
        raise ApiError(409, "idempotency_conflict", "Submission id already used with other content")
    receipt = _receipt(session, existing, created=False)
    stored = existing.receipt_json
    if stored is not None:  # Beleg des ersten Sendens, unverändert (A3 T-13 F-01)
        extras: dict[str, Any] = {k: stored[k] for k in ("advice", "escalation") if k in stored}
        return replace(receipt, extras=extras)
    parts, _ = _advice_parts(session, content, patient, existing)
    if parts:  # ältere Zeile ohne gespeicherten Beleg: einmal festhalten
        try:
            existing.receipt_json = {**receipt.body(), **parts}
            session.commit()
        except Exception as error:
            session.rollback()
            logger.error("storing receipt failed (%s)", type(error).__name__)
    return replace(receipt, extras=parts)


def _lang(response: Response, patient: Patient) -> str:
    """T-36: Tipps in der Sprache des Sendens (UI), sonst Patientensprache."""
    return getattr(response, "lang", None) or patient.language


def _advice_parts(
    session: Session, content: Content, patient: Patient, response: Response
) -> tuple[dict[str, Any], list[str]]:
    """Tipps und Eskalation zum Beleg; bei Fehlschlag Akut-Hinweis ohne Tipps."""
    try:
        recommendations, acute = advice.evaluate_with_escalation(session, response, content)
        parts = advice.receipt_parts(
            content, recommendations, _lang(response, patient), acute=acute
        )
        shown = [r.rule_id for r in recommendations if r.status == advice.SHOWN]
    except Exception as error:
        session.rollback()
        logger.error("advice evaluation failed (%s)", type(error).__name__)
        return advice.fallback_parts(content, _lang(response, patient)), []
    return parts, shown


def _with_advice(
    session: Session,
    clock: Clock,
    principal: Principal,
    patient: Patient,
    content: Content,
    receipt: Receipt,
    response_id: str,
) -> Receipt:
    """Ergänzt den Beleg einer neuen Antwort um Tipps/Eskalation; Audit `advice_shown` (nur IDs)."""
    response = session.get(Response, response_id)
    if response is None or content.advice is None:
        return receipt
    parts, shown = _advice_parts(session, content, patient, response)
    try:
        response.receipt_json = {**receipt.body(), **parts}  # Beleg beim ersten Senden speichern
        record_audit(
            session,
            clock,
            principal.actor,
            "advice_shown",
            "response",
            target_id=response_id,
            subject_id=patient.id,
            details={
                "rules": ",".join(shown),
                "count": len(shown),
                "acute": parts.get("escalation", {}).get("level") == advice.LEVEL_ACUTE,
            },
        )
        session.commit()
    except Exception as error:  # Antwort ist gespeichert; Beleg trotzdem ausliefern
        session.rollback()
        logger.error("advice audit failed (%s)", type(error).__name__)
    return replace(receipt, extras=parts)


def submit(
    session: Session,
    clock: Clock,
    principal: Principal,
    patient: Patient,
    content: Content,
    submission: Submission,
) -> Receipt:
    replay = _replay(session, patient, submission, content)
    if replay is not None:
        return replay
    catalog = {
        (item["symptom_key"], a["attribute"])
        for item in content.items["items"]
        for a in item["attributes"]
    }
    validate(submission, select_items(session, patient.id, content), catalog)
    # Variante der angezeigten Fassung (Client), sonst wie im Fragebogen berechnet; vor dem Anlegen,
    # damit die neue Antwort nicht mitzählt
    mode = submission.recall or recall_mode(session, patient.id, clock.now())
    response = Response(
        patient_id=patient.id,
        client_submission_id=submission.client_submission_id,
        channel=submission.channel,
        entered_by=submission.entered_by,
        recorded_at=clock.now(),
        questionnaire_id=submission.questionnaire_id,
        source=submission.source,
        lang=submission.lang,
        free_text_id=submission.free_text_id,
        recall=mode,
        synthetic=True,
    )
    try:
        session.add(response)
        session.flush()
    except IntegrityError:
        # Paralleler Request mit derselben ID war schneller: dessen Beleg gilt (oder 409).
        session.rollback()
        replay = _replay(session, patient, submission, content)
        if replay is None:
            raise
        return replay
    session.add_all(
        Answer(
            response_id=response.id,
            symptom_key=a.symptom_key,
            attribute=a.attribute,
            value=a.value,
            wording=wording_for(content, a.symptom_key, a.attribute, mode),
        )
        for a in submission.answers
    )
    session.flush()
    receipt = _receipt(session, response, created=True)
    record_audit(
        session,
        clock,
        principal.actor,
        "submit_response",
        "response",
        target_id=response.id,
        subject_id=patient.id,
        details={"answered": receipt.answered, "skipped": receipt.skipped},
    )
    response_id = response.id
    session.commit()  # die Eingabe ist gesichert, bevor irgendeine Regel läuft (H-5)
    evaluation.evaluate_safely(session, clock, principal.actor, response_id)
    return _with_advice(session, clock, principal, patient, content, receipt, response_id)


def list_own(session: Session, patient: Patient) -> list[dict[str, Any]]:
    responses = session.scalars(
        select(Response)
        .where(Response.patient_id == patient.id)
        .order_by(Response.recorded_at.desc(), literal_column("wa_responses.rowid").desc())
    ).all()
    result: list[dict[str, Any]] = []
    for response in responses:
        rows = session.scalars(
            select(Answer)
            .where(Answer.response_id == response.id)
            .order_by(Answer.symptom_key, Answer.attribute)
        ).all()
        result.append(
            {
                "response_id": response.id,
                "recorded_at": iso_prague(response.recorded_at),
                "channel": response.channel,
                "entered_by": response.entered_by,
                "answers": [
                    {"symptom_key": a.symptom_key, "attribute": a.attribute, "value": a.value}
                    for a in rows
                ],
            }
        )
    return result
