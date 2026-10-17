"""Seed (nur `DEMO_MODE`, idempotent) aus `scenario.yaml`. Alle Zeilen `synthetic=true`.

Zeiten: `anchor` plus `day_offset` Kalendertage in Europe/Prague (Uhrzeit bleibt über die
Sommerzeitumstellung gleich); `hour` setzt die Ortsstunde, sonst gilt die Uhrzeit des Ankers.
Gespeichert wird der Zeitpunkt (UTC). Meldungen entstehen über dieselbe Regel-Engine wie
im Live-Betrieb (G-08).
"""

import logging
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import Clock
from app.persistence.models import User
from app.services.audit import ACTOR_SYSTEM, Actor
from waechter.constants import CONFIG_KIND_REPORT, CONFIG_KIND_RULES
from waechter.content import Content, get_content
from waechter.models import (
    Answer,
    ConfigVersion,
    Patient,
    Response,
    Therapy,
    Visit,
)
from waechter.services import evaluation, triage
from waechter.services import summary as summary_service
from waechter.timeutil import from_prague_local, to_prague

logger = logging.getLogger("waechter.seed")

#: Demo-Konten laut Vertrag (README §2, G-14), falls `scenario.yaml` keinen `username` nennt
DEMO_SUMMARY_PSEUDONYM = "SYN-0001"
DEFAULT_USERNAMES = {"SYN-0001": "patient", "SYN-0002": "patient2", "SYN-0006": "patient6"}


def shift(anchor: datetime, day_offset: int, hour: int | None = None) -> datetime:
    """`anchor` plus `day_offset` Kalendertage in Europe/Prague (G-04), optional mit fester Stunde.

    Gerechnet wird mit der Ortszeit (Uhrzeit bleibt über die Sommerzeitumstellung gleich), danach
    zurück in den Zeitpunkt umgerechnet.
    """
    local = to_prague(anchor).replace(tzinfo=None) + timedelta(days=day_offset)
    if hour is not None:
        local = local.replace(hour=hour, minute=0, second=0, microsecond=0)
    return from_prague_local(local)


def _seed_config_versions(session: Session, content: Content, clock: Clock) -> None:
    for kind, body in ((CONFIG_KIND_RULES, content.rules), (CONFIG_KIND_REPORT, content.report)):
        version: str = body["version"]
        exists = session.scalar(
            select(ConfigVersion.id).where(
                ConfigVersion.kind == kind, ConfigVersion.version == version
            )
        )
        if exists is not None:
            continue
        has_active = session.scalar(
            select(ConfigVersion.id).where(
                ConfigVersion.kind == kind, ConfigVersion.active.is_(True)
            )
        )
        session.add(
            ConfigVersion(
                kind=kind,
                version=version,
                body_json=body,
                active=has_active is None,
                created_at=clock.now(),
                change_note="seed",
            )
        )


def _questionnaire_id(content: Content, regimen_id: str) -> str:
    return f"{content.items['version']}:{regimen_id}"


def _seed_patient(
    session: Session,
    content: Content,
    clock: Clock,
    spec: dict[str, Any],
    anchor: datetime,
) -> None:
    username = spec.get("username") or DEFAULT_USERNAMES.get(spec["pseudonym"])
    user_id = session.scalar(select(User.id).where(User.username == username)) if username else None
    taken = (
        session.scalar(select(Patient.id).where(Patient.user_id == user_id)) if user_id else None
    )
    patient = Patient(
        pseudonym=spec["pseudonym"],
        display_name=spec["display_name"],
        birth_year=spec["birth_year"],
        sex=spec["sex"],
        language=spec["language"],
        diagnosis_text=spec.get("diagnosis_text"),
        diagnosis_code=spec.get("diagnosis_code"),
        user_id=user_id if taken is None else None,
        synthetic=True,
    )
    session.add(patient)
    session.flush()
    session.add(
        Therapy(
            patient_id=patient.id,
            regimen_id=spec["regimen_id"],
            cycle_start=shift(anchor, spec["cycle_start_offset"]),
            synthetic=True,
        )
    )
    for visit in spec["visits"]:
        session.add(
            Visit(
                patient_id=patient.id,
                at=shift(anchor, visit["day_offset"]),
                kind=visit["kind"],
                synthetic=True,
            )
        )
    questionnaire = _questionnaire_id(content, spec["regimen_id"])
    for index, response in enumerate(spec["responses"]):
        row = Response(
            patient_id=patient.id,
            client_submission_id=f"seed-{spec['pseudonym']}-{index}",
            channel=response.get("channel", "web"),
            entered_by=response.get("entered_by", "self"),
            recorded_at=shift(anchor, response["day_offset"], response.get("hour")),
            questionnaire_id=questionnaire,
            synthetic=True,
        )
        session.add(row)
        session.flush()
        for key, value in response["answers"].items():
            symptom_key, attribute = key.split(".", 1)
            session.add(
                Answer(
                    response_id=row.id,
                    symptom_key=symptom_key,
                    attribute=attribute,
                    value=value,
                )
            )
    session.commit()  # Daten zuerst sichern, dann auswerten (wie im Live-Pfad, H-5)
    # Meldungen über denselben Pfad wie im Live-Betrieb, chronologisch (G-08).
    response_ids = session.scalars(
        select(Response.id)
        .where(Response.patient_id == patient.id)
        .order_by(Response.recorded_at, Response.id)
    ).all()
    session.info[triage.SEED_FLAG] = True  # Entscheidungen ja, Meldungen nein (Bestandsorakel)
    session.info[triage.SEED_LAST] = response_ids[-1] if response_ids else None
    try:
        for response_id in response_ids:
            evaluation.evaluate_safely(session, clock, Actor(None, ACTOR_SYSTEM), response_id)
    finally:
        session.info.pop(triage.SEED_FLAG, None)
        session.info.pop(triage.SEED_LAST, None)
    if spec["pseudonym"] == DEMO_SUMMARY_PSEUDONYM:
        _seed_summary(session, clock, content, patient.id)


def _seed_summary(session: Session, clock: Clock, content: Content, patient_id: str) -> None:
    """Kurzfassung der Demo-Patientin im konfigurierten Modus (template | cached | openai)."""
    try:
        summary_service.generate(
            session, clock, Actor(None, ACTOR_SYSTEM), patient_id, content, "cs"
        )
    except Exception as error:  # Demo-Start darf an der KI-Kurzfassung nie scheitern
        session.rollback()
        logger.error("demo summary failed (%s)", type(error).__name__)


def seed_scenario(session: Session, clock: Clock) -> None:
    """Seed-Schritt der Registry: legt fehlende Demo-Patient:innen samt Verlauf an (idempotent)."""
    content = get_content()
    if content is None:
        logger.warning("content directory missing: wächter seed skipped")
        return
    _seed_config_versions(session, content, clock)
    session.flush()
    anchor = datetime.fromisoformat(content.scenario["anchor"])
    for spec in content.scenario["patients"]:
        known = session.scalar(select(Patient.id).where(Patient.pseudonym == spec["pseudonym"]))
        if known is None:
            _seed_patient(session, content, clock, spec, anchor)
    session.flush()
