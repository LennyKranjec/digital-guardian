"""Regelauswertung nach dem Speichern, getrennt von der Antwort (A0-Entscheid H-5, Safety).

Die Eingabe der Patientin darf nie durch einen Regelfehler verloren gehen. Deshalb ist die Antwort
bereits committet, wenn dieser Pfad läuft; die Auswertung hat eine eigene Transaktion. Bei einer
Ausnahme wird nur die Regel-Transaktion zurückgerollt, der Fehler ohne Werte geloggt (nur Typname),
die Antwort mit `evaluation_status = failed` markiert und `rule_evaluation_failed` auditiert. Die
Arbeitsliste (T-05) zeigt solche Patientinnen mindestens grau ("Auswertung ausstehend"). Live und
Seed nutzen denselben Pfad.
"""

import logging
from typing import Final

from sqlalchemy import update
from sqlalchemy.orm import Session

from app.core.clock import Clock
from app.services.audit import Actor, record_audit
from waechter.models import Patient, Response
from waechter.services import alerts, hooks, triage

logger = logging.getLogger("waechter.evaluation")

STATUS_DONE: Final = "done"
STATUS_FAILED: Final = "failed"


def evaluate_safely(session: Session, clock: Clock, actor: Actor, response_id: str) -> bool:
    """Wertet die gespeicherte Antwort aus; `True` bei Erfolg, `False` bei markiertem Fehler."""
    response = session.get(Response, response_id)
    if response is None:
        return False
    try:
        _lock_patient(session, response.patient_id)
        hooks.on_response_saved(session, response)
        session.commit()
    except Exception as error:
        session.rollback()
        alerts.discard_pending_notices(session)
        logger.error("rule evaluation failed (%s)", type(error).__name__)
        _mark_failed(session, clock, actor, response_id, type(error).__name__)
        return False
    alerts.dispatch_pending_notices(session)
    triage.decide_safely(
        session, clock, actor, response_id
    )  # eigene Transaktion, nie vor den Regeln
    return True


def _lock_patient(session: Session, patient_id: str) -> None:
    """Serialisiert die Auswertungen je Patientin (Schreibsperre bis zum Commit).

    Ohne Sperre könnten gleichzeitige Auswertungen derselben Patientin die offene Meldung der
    jeweils anderen nicht sehen und Dubletten anlegen (Dedupe prüft vor dem Schreiben).
    Ein wirkungsloses UPDATE sperrt in SQLite die Datenbank, in PostgreSQL die Zeile.
    """
    session.execute(
        update(Patient).where(Patient.id == patient_id).values(synthetic=Patient.synthetic)
    )


def _mark_failed(
    session: Session, clock: Clock, actor: Actor, response_id: str, error_type: str
) -> None:
    try:
        response = session.get(Response, response_id)
        session.execute(
            update(Response)
            .where(Response.id == response_id)
            .values(evaluation_status=STATUS_FAILED)
        )
        record_audit(
            session,
            clock,
            actor,
            "rule_evaluation_failed",
            "response",
            target_id=response_id,
            subject_id=response.patient_id if response is not None else None,
            details={"error": error_type},
        )
        session.commit()
    except Exception as error:  # die Antwort selbst ist gespeichert; nur laut melden
        session.rollback()
        logger.error("marking failed evaluation failed (%s)", type(error).__name__)
