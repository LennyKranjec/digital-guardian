"""KI-Kurzfassung je Patientin: Fakten ⇒ Prompt ⇒ Adapter ⇒ Prüfer ⇒ Speichern mit Provenance.

Die Kurzfassung ist ein Entwurf zur Entscheidungsunterstützung. Sie enthält nur Sätze, die der
deterministische Prüfer (`llm/verifier.py`) bestätigt hat; die Ampel bestimmt sie nie.
`POST` dedupliziert: gleiche Fakten, gleiche Prompt-Version und gleicher angeforderter Modus liefern
dieselbe `summary_id` (der Schlüssel steht eindeutig in der Datenbank, auch bei Parallelität).
Ausnahme: ein fehlgeschlagener Versuch eines Sprachmodells (Rückfall auf den Textbaustein) wird
nicht dedupliziert; das nächste `POST` versucht es erneut (T-07F, F-02).
Entwürfe eines Sprachmodells (`live`/`cached`) durchlaufen zusätzlich die extraktive Wortprüfung;
bleibt kein Satz übrig, gilt der Textbaustein (Modus `fallback`).
"""

import hashlib
import logging
from typing import Any, Final
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.clock import Clock
from app.core.errors import ApiError
from app.services.access import not_found
from app.services.audit import Actor, record_audit
from waechter.content import Content
from waechter.llm import adapters
from waechter.llm.facts import build_facts
from waechter.llm.prompt import PROMPT_VERSION, build_prompt
from waechter.llm.verifier import verify
from waechter.models import Patient, Summary
from waechter.services.summary_queries import latest_summary, summary_view

logger = logging.getLogger("waechter.summary")

#: Modi, in denen ein Sprachmodell den Text schrieb (extraktive Prüfung, Wiederholung bei Ausfall)
LLM_MODES: Final = ("live", "cached")


def _digest(*parts: str) -> str:
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


def get_latest(session: Session, patient_id: str) -> dict[str, Any]:
    summary = latest_summary(session, patient_id)
    if summary is None:
        raise ApiError(404, "summary_none", "No summary yet")
    return summary_view(summary)


def generate(
    session: Session,
    clock: Clock,
    actor: Actor,
    patient_id: str,
    content: Content,
    lang: str,
) -> tuple[dict[str, Any], bool]:
    """Erzeugt (oder findet) die Kurzfassung; `(Ansicht, neu angelegt)`."""
    patient = session.get(Patient, patient_id)
    if patient is None:
        raise not_found()
    facts = build_facts(session, clock, content, patient, lang)
    requested = adapters.requested_mode()
    cache_key = _digest(PROMPT_VERSION, facts.hash)
    dedupe_key = _digest(cache_key, requested)
    existing = session.scalar(
        select(Summary).where(Summary.patient_id == patient.id, Summary.dedupe_key == dedupe_key)
    )
    created = existing is None
    summary = existing
    if summary is None:
        prompt = build_prompt(facts.facts, facts.lang)
        draft = adapters.generate(facts, prompt, cache_key)
        llm_draft = draft.mode in LLM_MODES
        checked = verify(draft.text, facts.mapping(), facts.unknown_topics, extractive=llm_draft)
        if llm_draft and not checked.sentences:  # nichts Belegtes übrig ⇒ Textbaustein
            logger.warning("llm draft had no verifiable sentence (%d dropped)", checked.dropped)
            draft = adapters.template_draft(facts, prompt, cache_key)
            checked = verify(draft.text, facts.mapping(), facts.unknown_topics, extractive=False)
        if draft.mode == "fallback" and requested != "template":
            dedupe_key = _digest(dedupe_key, "failed", uuid4().hex)  # nie als Treffer werten
        summary = Summary(
            patient_id=patient.id,
            created_at=clock.now(),
            generator=draft.generator[:64],
            mode=draft.mode,
            facts_hash=facts.hash,
            dedupe_key=dedupe_key,
            body_json={
                "sentences": [
                    {"text": s.text, "refs": list(s.refs), "verified": s.verified}
                    for s in checked.sentences
                ],
                "dropped_sentences": checked.dropped,
                "unknown_topics": checked.unknown_topics,
                "fact_count": len(facts.facts),
                "provenance": {
                    "generator": draft.generator,
                    "model": draft.model,
                    "mode": draft.mode,
                    "requested_mode": requested,
                    "facts_hash": facts.hash,
                    "prompt_version": PROMPT_VERSION,
                    "lang": facts.lang,
                },
            },
            synthetic=True,
        )
        try:
            session.add(summary)
            session.flush()
        except IntegrityError:  # paralleler Request war schneller: dessen Zusammenfassung gilt
            session.rollback()
            summary = session.scalar(
                select(Summary).where(
                    Summary.patient_id == patient.id, Summary.dedupe_key == dedupe_key
                )
            )
            if summary is None:
                raise
            created = False
    record_audit(
        session,
        clock,
        actor,
        "generate_summary",
        "summary",
        target_id=summary.id,
        subject_id=patient.id,
        details={
            "mode": summary.mode,
            "sentences": len(summary.body_json["sentences"]),
            "dropped": summary.body_json["dropped_sentences"],
            "deduplicated": not created,
        },
    )
    session.commit()
    return summary_view(summary), created
