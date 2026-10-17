"""Freitext der Patientin (T-22, Vertrag v2.9): speichern, zuordnen (Vorschlag), Folgefragen.

Ablauf `submit`: Antwort der Patientin prüfen (fremde ⇒ 404) ⇒ Text bereinigen und Länge prüfen ⇒
Adapter ordnet dem GESAMTEN Symptomkatalog zu (nur Vorschlag) ⇒ deterministischer Prüfer ⇒
dauerhaft speichern (`wa_free_texts`, nie gelöscht) ⇒ Audit **ohne Inhalt**.

Kontrollierter Einfluss auf die Triage (Mensch-Vorgabe): Das Sprachmodell setzt nie eine Stufe,
Antwort oder Meldung. Jede geprüfte Zuordnung erzeugt eine **Folgefrage-Karte** (Standardfragen
über dieselbe Options-/Fragetextfunktion wie der Check-in); kritische Symptome stehen zuerst, damit
Boden und Akut-Weiche über die Antwort greifen. Erst die Antwort der Patientin (normale Antwort mit
`source = free_text_followup`) geht in Regeln und Triage-Baum ein. Unbeantwortete Zuordnungen
heißen „unbestätigt“ (Hinweis, kein Alarm); offene Karten erscheinen beim nächsten Check-in wieder.

Schalter `WAECHTER_FREETEXT` (`1`/`true`/`on` an, `0`/`false`/`off` aus); ohne Angabe gilt der
Demo-Modus (`DEMO_MODE`).
"""

import os
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Final

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.clock import Clock
from app.core.errors import ApiError, FieldError
from app.services.access import not_found
from app.services.audit import record_audit
from app.services.auth import Principal
from waechter.content import Content
from waechter.freetext import mapper, verify
from waechter.freetext.mapper import Candidate
from waechter.freetext.text import clean_text
from waechter.models import Answer, FreeText, Patient, Response, free_text_newest_first
from waechter.services import questionnaire, responses
from waechter.services.patient_views import get_patient, symptom_label
from waechter.timeutil import iso_prague

FLAG_ENV: Final = "WAECHTER_FREETEXT"
DEFAULT_MAX_LENGTH: Final = 500
#: Karten für diese Symptome kommen zuerst (Boden/Akut-Weiche greift über die Antwort)
CRITICAL_FIRST: Final = ("fever", "shortness_of_breath", "vomiting")
#: So viele Freitexte (neueste) bieten offene Folgefragen an
MAX_OPEN_TEXTS: Final = 5
_ON: Final = frozenset({"1", "true", "on", "yes"})
_OFF: Final = frozenset({"0", "false", "off", "no"})

Pair = tuple[str, str]


def enabled(demo_mode: bool) -> bool:
    value = os.environ.get(FLAG_ENV, "").strip().lower()
    if value in _ON:
        return True
    if value in _OFF:
        return False
    return demo_mode


def max_length(content: Content) -> int:
    return int(content.freetext["max_length"]) if content.freetext else DEFAULT_MAX_LENGTH


def features(content: Content | None, demo_mode: bool) -> dict[str, Any]:
    """`GET /meta` ⇒ `waechter.free_text`: Schalter und Höchstlänge für die Oberfläche."""
    return {
        "enabled": enabled(demo_mode),
        "max_length": max_length(content) if content is not None else DEFAULT_MAX_LENGTH,
    }


@dataclass(frozen=True)
class Saved:
    row: FreeText
    created: bool


def _lang(language: str | None) -> str:
    return language if language in ("cs", "en", "de") else "cs"


def candidates_for(session: Session, patient_id: str, content: Content) -> list[Candidate]:
    """Der GESAMTE Katalog; Items des Fragebogens der Patientin (getrackt) zuerst."""
    selection = questionnaire.select_items(session, patient_id, content)
    asked = [item["symptom_key"] for item, _ in selection.items]
    catalog = {item["symptom_key"]: item for item in content.items["items"]}
    order = [*asked, *(key for key in catalog if key not in asked)]
    return [
        Candidate(
            symptom_key=key,
            label_cs=str(catalog[key]["label"]["cs"]),
            label_en=str(catalog[key]["label"]["en"]),
            attributes=tuple(a["attribute"] for a in catalog[key]["attributes"]),
            in_questionnaire=key in asked,
        )
        for key in order
        if key in catalog
    ]


def _field_error(code: str, message: str) -> ApiError:
    error = FieldError(field="text", code=code, message=message)
    return ApiError(422, "validation_failed", message, [error])


def _checked_text(raw: str, content: Content) -> str:
    text = clean_text(raw)
    if not text:
        raise _field_error("required", "Text must not be empty")
    if len(text) > max_length(content):
        raise _field_error("too_long", "Text is too long")
    return text


def _own_response(session: Session, patient: Patient, response_id: str) -> Response:
    response = session.get(Response, response_id)
    if response is None or response.patient_id != patient.id:
        raise not_found()
    return response


def _own_free_text(session: Session, patient: Patient, free_text_id: str) -> FreeText:
    row = session.get(FreeText, free_text_id)
    if row is None or row.patient_id != patient.id:
        raise not_found()
    return row


def _existing(session: Session, response_id: str) -> FreeText | None:
    return session.scalars(select(FreeText).where(FreeText.response_id == response_id)).first()


def _replay(row: FreeText, text: str) -> Saved:
    if row.text != text:
        raise ApiError(409, "free_text_exists", "A free text is already stored for this response")
    return Saved(row, False)


def submit(
    session: Session,
    clock: Clock,
    principal: Principal,
    patient: Patient,
    content: Content,
    *,
    response_id: str,
    text: str,
    lang: str | None = None,
) -> Saved:
    """Speichert den Freitext zu einer eigenen Antwort (idempotent je Antwort)."""
    response = _own_response(session, patient, response_id)
    language = _lang(lang or patient.language)
    cleaned = _checked_text(text, content)
    known = _existing(session, response.id)
    if known is not None:
        return _replay(known, cleaned)
    candidates = candidates_for(session, patient.id, content)
    outcome = mapper.map_free_text(
        cleaned,
        candidates,
        content.freetext,
        allow_llm=bool(patient.synthetic),
        critical=_critical(content),
    )
    catalog = {c.symptom_key: c.attributes for c in candidates}
    checked = verify.verify_suggestions(cleaned, outcome.raw, catalog)
    tracked = {c.symptom_key for c in candidates if c.in_questionnaire}
    row = FreeText(
        patient_id=patient.id,
        response_id=response.id,
        text=cleaned,
        lang=language,
        created_at=clock.now(),
        suggestions_json=[
            {
                **s.body(),
                "in_questionnaire": s.symptom_key in tracked,
                "source": _source_of(s.symptom_key, outcome),
            }
            for s in checked.suggestions
        ],
        mapper=outcome.mapper,
        mapper_mode=outcome.mode,
        rejected_suggestions=checked.rejected,
        synthetic=True,
    )
    session.add(row)
    record_audit(
        session,
        clock,
        principal.actor,
        "free_text_saved",
        "response",
        target_id=response.id,
        subject_id=patient.id,
        details={
            "length": len(cleaned),
            "suggestions": len(checked.suggestions),
            "rejected": checked.rejected,
            "mode": outcome.mode,
        },
    )
    try:
        session.commit()
    except IntegrityError:  # paralleler Aufruf hat die Antwort zuerst bekommen
        session.rollback()
        winner = _existing(session, response.id)
        if winner is None:
            raise
        return _replay(winner, cleaned)
    return Saved(row, True)


# ---- Folgefragen ---------------------------------------------------------------------------
def _item(content: Content, symptom_key: str) -> dict[str, Any] | None:
    return next((i for i in content.items["items"] if i["symptom_key"] == symptom_key), None)


def _critical(content: Content) -> list[str]:
    acute = content.advice["escalation"].get("always_acute_for", []) if content.advice else []
    return list(dict.fromkeys([*CRITICAL_FIRST, *acute]))


def card_pairs(row: FreeText, content: Content) -> dict[str, list[str]]:
    """`symptom_key ⇒ Attribute` der Folgefragen eines Freitexts (kritische zuerst, dann Textfolge).

    Nennt ein Vorschlag ein Attribut, wird nur danach gefragt, sonst nach allen des Items.
    """
    wanted: dict[str, list[str]] = {}
    for s in sorted(row.suggestions_json, key=lambda s: s["start"]):
        item = _item(content, s["symptom_key"])
        if item is None:
            continue
        attributes = [a["attribute"] for a in item["attributes"]]
        asked = [s["attribute"]] if s.get("attribute") in attributes else attributes
        merged = wanted.setdefault(s["symptom_key"], [])
        merged.extend(a for a in asked if a not in merged)
    critical = _critical(content)
    ordered = sorted(wanted, key=lambda k: critical.index(k) if k in critical else len(critical))
    return {key: wanted[key] for key in ordered}


def answered_pairs(session: Session, free_text_id: str) -> dict[Pair, int | None]:
    """Antworten auf die Folgefragen dieses Freitexts (jüngste je Feld; `null` = übersprungen)."""
    rows = session.execute(
        select(Answer.symptom_key, Answer.attribute, Answer.value)
        .join(Response, Response.id == Answer.response_id)
        .where(Response.free_text_id == free_text_id, Response.source == responses.SOURCE_FOLLOWUP)
        .order_by(Response.recorded_at, Response.id)
    ).all()
    return {(key, attribute): value for key, attribute, value in rows}


def pending_pairs(session: Session, row: FreeText, content: Content) -> list[Pair]:
    """Noch offene Felder; auch eine übersprungene Frage gilt als beantwortet (kein Drängen)."""
    done = answered_pairs(session, row.id)
    return [
        (key, attribute)
        for key, attributes in card_pairs(row, content).items()
        for attribute in attributes
        if (key, attribute) not in done
    ]


def _source_of(symptom_key: str, outcome: mapper.MapOutcome) -> str:
    """Quelle der Zuordnung: `model` (Sprachmodell nannte das Symptom) oder `wordlist`."""
    return (
        "model"
        if outcome.mode == mapper.MODE_LIVE and symptom_key in outcome.model_keys
        else "wordlist"
    )


def _quote_of(row: FreeText, symptom_key: str) -> str:
    return str(next(s["quote"] for s in row.suggestions_json if s["symptom_key"] == symptom_key))


def cards_of(
    session: Session, row: FreeText, content: Content, lang: str, now: datetime
) -> list[dict[str, Any]]:
    """Offene Folgefrage-Karten eines Freitexts (Standardfragen, kritische zuerst)."""
    pending = pending_pairs(session, row, content)
    critical = _critical(content)
    mode = questionnaire.recall_mode(
        session, row.patient_id, now
    )  # Rückblick wie der Check-in (T-23)
    cards: list[dict[str, Any]] = []
    for key in dict.fromkeys(k for k, _ in pending):
        item = _item(content, key)
        if item is None:
            continue
        wanted = {a for k, a in pending if k == key}
        cards.append(
            {
                "free_text_id": row.id,
                "symptom_key": key,
                "label": symptom_label(content, key, lang),
                "quote": _quote_of(row, key),
                "critical": key in critical,
                "questions": [
                    {
                        "attribute": a["attribute"],
                        "text": questionnaire.question_text(a, lang, mode),
                        "options": questionnaire.options_for(content, a["attribute"], lang, key),
                    }
                    for a in item["attributes"]
                    if a["attribute"] in wanted
                ],
            }
        )
    return cards


def open_cards(
    session: Session, patient: Patient, content: Content, lang: str | None, now: datetime
) -> list[dict[str, Any]]:
    """Alle offenen Folgefrage-Karten der Patientin (kritische Symptome zuerst)."""
    language = _lang(lang or patient.language)
    rows = session.scalars(
        select(FreeText)
        .where(FreeText.patient_id == patient.id)
        .order_by(*free_text_newest_first())
        .limit(MAX_OPEN_TEXTS)
    ).all()
    cards = [card for row in rows for card in cards_of(session, row, content, language, now)]
    critical = _critical(content)
    cards.sort(key=lambda c: critical.index(c["symptom_key"]) if c["critical"] else len(critical))
    return cards


def answer_followups(
    session: Session,
    clock: Clock,
    principal: Principal,
    patient: Patient,
    content: Content,
    *,
    free_text_id: str,
    client_submission_id: str,
    answers: Iterable[responses.AnswerIn],
) -> responses.Receipt:
    """Antwort der Patientin auf Folgefragen: normale Antwort mit `source = free_text_followup`."""
    row = _own_free_text(session, patient, free_text_id)
    given = tuple(answers)
    replay = session.scalar(
        select(Response.id).where(
            Response.patient_id == patient.id,
            Response.client_submission_id == client_submission_id,
        )
    )
    if replay is None:
        allowed = set(pending_pairs(session, row, content))
        done = answered_pairs(session, row.id)
        errors: list[FieldError] = []
        for index, a in enumerate(given):
            pair = (a.symptom_key, a.attribute)
            if pair in allowed:
                continue
            code = "followup_answered" if pair in done else "unknown_item"
            errors.append(
                FieldError(field=f"answers.{index}.symptom_key", code=code, message="Not open")
            )
        if errors:
            status = 409 if any(e.code == "followup_answered" for e in errors) else 422
            raise ApiError(status, "followup_not_open", "Follow-up question is not open", errors)
    selection = questionnaire.select_items(session, patient.id, content)
    return responses.submit(
        session,
        clock,
        principal,
        patient,
        content,
        responses.Submission(
            client_submission_id=client_submission_id,
            questionnaire_id=selection.questionnaire_id,
            channel="web",
            entered_by="self",
            answers=given,
            source=responses.SOURCE_FOLLOWUP,
            free_text_id=row.id,
            lang=row.lang,
        ),
    )


# ---- Anzeige für die Klinik ----------------------------------------------------------------
def _confirmation(
    row: FreeText, content: Content, done: dict[Pair, int | None], suggestion: dict[str, Any]
) -> dict[str, Any]:
    key = suggestion["symptom_key"]
    pairs = card_pairs(row, content).get(key, [])
    answers = [{"attribute": a, "value": done[(key, a)]} for a in pairs if (key, a) in done]
    return {"confirmed": bool(pairs) and len(answers) == len(pairs), "answers": answers}


def view(session: Session, row: FreeText, content: Content, lang: str) -> dict[str, Any]:
    """Darstellung für das Cockpit: Vorschläge mit Etikett, Zitatposition und Bestätigung."""
    done = answered_pairs(session, row.id)
    suggestions = [
        {
            "symptom_key": s["symptom_key"],
            "label": symptom_label(content, s["symptom_key"], lang),
            "attribute": s.get("attribute"),
            "proposed_value": s.get("proposed_value"),
            "quote": s["quote"],
            "start": s["start"],
            "end": s["end"],
            "in_questionnaire": bool(s.get("in_questionnaire")),
            "source": s.get("source") or ("model" if row.mapper_mode == "live" else "wordlist"),
            **_confirmation(row, content, done, s),
        }
        for s in row.suggestions_json
    ]
    return {
        "free_text_id": row.id,
        "response_id": row.response_id,
        "patient_id": row.patient_id,
        "text": row.text,
        "lang": row.lang,
        "created_at": iso_prague(row.created_at),
        "suggestions": suggestions,
        "mapper": row.mapper,
        "mode": row.mapper_mode,
        "rejected_suggestions": row.rejected_suggestions,
        "unconfirmed": len({s["symptom_key"] for s in suggestions if not s["confirmed"]}),
    }


def list_for_patient(
    session: Session,
    clock: Clock,
    principal: Principal,
    patient_id: str,
    content: Content,
    lang: str,
    *,
    is_enabled: bool,
) -> list[dict[str, Any]]:
    """Freitexte einer Patientin, neueste zuerst; der Abruf wird ohne Inhalt auditiert."""
    patient = get_patient(session, patient_id)
    if not is_enabled:
        return []
    rows = session.scalars(
        select(FreeText)
        .where(FreeText.patient_id == patient.id)
        .order_by(*free_text_newest_first())
    ).all()
    record_audit(
        session,
        clock,
        principal.actor,
        "free_texts_view",
        "patient",
        target_id=patient.id,
        subject_id=patient.id,
        details={"count": len(rows)},
    )
    session.commit()
    return [view(session, r, content, lang) for r in rows]


def unconfirmed_counts(
    session: Session, patient_ids: Iterable[str], content: Content
) -> dict[str, int]:
    """Je Patientin: Zahl unbestätigter Freitext-Zuordnungen (Hinweis, kein Alarm); nur Treffer."""
    counts: dict[str, int] = {}
    for patient_id in patient_ids:
        rows = session.scalars(select(FreeText).where(FreeText.patient_id == patient_id)).all()
        total = sum(len({k for k, _ in pending_pairs(session, row, content)}) for row in rows)
        if total:
            counts[patient_id] = total
    return counts


def mentions(
    session: Session,
    patient_id: str,
    symptom_keys: Iterable[str],
    content: Content,
    *,
    limit: int = 3,
) -> list[dict[str, Any]]:
    """Zitate aus Freitexten zu diesen Symptomen („Patientin schrieb …“), neueste zuerst."""
    wanted = set(symptom_keys)
    rows = session.scalars(
        select(FreeText)
        .where(FreeText.patient_id == patient_id)
        .order_by(*free_text_newest_first())
        .limit(MAX_OPEN_TEXTS * 2)
    ).all()
    found: list[dict[str, Any]] = []
    for row in rows:
        done = answered_pairs(session, row.id)
        for s in row.suggestions_json:
            if s["symptom_key"] not in wanted:
                continue
            found.append(
                {
                    "free_text_id": row.id,
                    "symptom_key": s["symptom_key"],
                    "quote": s["quote"],
                    "created_at": iso_prague(row.created_at),
                    "mode": row.mapper_mode,
                    "proposed_value": s.get("proposed_value"),
                    **_confirmation(row, content, done, s),
                }
            )
    return found[:limit]


def since(session: Session, patient_id: str, start: datetime | None, limit: int) -> list[FreeText]:
    """Freitexte seit `start` (oder alle), neueste zuerst, höchstens `limit` (Kurzfassung)."""
    query = select(FreeText).where(FreeText.patient_id == patient_id)
    if start is not None:
        query = query.where(FreeText.created_at >= start)
    return list(session.scalars(query.order_by(*free_text_newest_first()).limit(limit)))
