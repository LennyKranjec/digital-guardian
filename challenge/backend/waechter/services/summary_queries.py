"""Lesen der KI-Kurzfassung im Vertragsformat (Schema `Summary`)."""

from typing import Any, Final

from sqlalchemy import select
from sqlalchemy.orm import Session

from waechter.models import Summary
from waechter.timeutil import iso_prague

DISCLAIMER_KEY: Final = "summary.disclaimer"  # UI-Text: KI-Entwurf, Belege prüfen


def summary_view(summary: Summary) -> dict[str, Any]:
    body = summary.body_json
    return {
        "summary_id": summary.id,
        "generated_at": iso_prague(summary.created_at),
        "generator": summary.generator,
        "mode": summary.mode,
        "sentences": body["sentences"],
        "dropped_sentences": body["dropped_sentences"],
        "unknown_topics": body["unknown_topics"],
        "fact_count": body["fact_count"],
        "disclaimer_key": DISCLAIMER_KEY,
        "provenance_id": f"prov-{summary.id}",
        "provenance": body["provenance"],
    }


def latest_summary(session: Session, patient_id: str) -> Summary | None:
    return session.scalars(
        select(Summary)
        .where(Summary.patient_id == patient_id)
        .order_by(Summary.created_at.desc(), Summary.id)
        .limit(1)
    ).first()
