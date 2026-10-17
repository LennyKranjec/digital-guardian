"""Datenmodell des Wächters (eigene Basis, Tabellenpräfix `wa_`). Alle Zeilen sind synthetisch.

`user_id` ist bewusst kein Fremdschlüssel: die Plattformtabelle `users` liegt in einer anderen
`MetaData`; die Zuordnung prüft der Subjekt-Resolver. Zeiten sind UTC (`UtcDateTime`).
"""

from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    literal_column,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.persistence.models import UtcDateTime, new_id


class WaechterBase(DeclarativeBase):
    """Basis der `wa_*`-Tabellen."""


def _id() -> Mapped[str]:
    return mapped_column(String(36), primary_key=True, default=new_id)


def _synthetic() -> Mapped[bool]:
    return mapped_column(Boolean, nullable=False, default=True, server_default=text("1"))


class Patient(WaechterBase):
    __tablename__ = "wa_patients"

    id: Mapped[str] = _id()
    pseudonym: Mapped[str] = mapped_column(String(16), unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(120), nullable=False)
    birth_year: Mapped[int] = mapped_column(Integer, nullable=False)
    sex: Mapped[str] = mapped_column(String(16), nullable=False)
    language: Mapped[str] = mapped_column(String(8), nullable=False)
    diagnosis_text: Mapped[str | None] = mapped_column(Text)
    diagnosis_code: Mapped[str | None] = mapped_column(String(16))  # ICD-10, synthetisch (v1.9)
    user_id: Mapped[str | None] = mapped_column(String(36), unique=True)
    #: T-34: Idempotenzschlüssel der Einschreibung durch das Personal (sonst `NULL`)
    enrollment_request_id: Mapped[str | None] = mapped_column(String(64), unique=True, index=True)
    synthetic: Mapped[bool] = _synthetic()


class Therapy(WaechterBase):
    __tablename__ = "wa_therapies"

    id: Mapped[str] = _id()
    patient_id: Mapped[str] = mapped_column(
        ForeignKey("wa_patients.id", ondelete="CASCADE"), nullable=False, index=True
    )
    regimen_id: Mapped[str] = mapped_column(String(64), nullable=False)
    cycle_start: Mapped[datetime] = mapped_column(UtcDateTime, nullable=False)
    synthetic: Mapped[bool] = _synthetic()


class Visit(WaechterBase):
    __tablename__ = "wa_visits"

    id: Mapped[str] = _id()
    patient_id: Mapped[str] = mapped_column(
        ForeignKey("wa_patients.id", ondelete="CASCADE"), nullable=False, index=True
    )
    at: Mapped[datetime] = mapped_column(UtcDateTime, nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)  # past | planned
    synthetic: Mapped[bool] = _synthetic()


class Response(WaechterBase):
    __tablename__ = "wa_responses"
    __table_args__ = (
        Index("ix_wa_responses_patient_at", "patient_id", "recorded_at"),
        # Idempotenzschlüssel gilt je Patientin (A3 F-02): fremde IDs kollidieren nie
        UniqueConstraint("patient_id", "client_submission_id"),
    )

    id: Mapped[str] = _id()
    patient_id: Mapped[str] = mapped_column(
        ForeignKey("wa_patients.id", ondelete="CASCADE"), nullable=False
    )
    client_submission_id: Mapped[str] = mapped_column(String(64), nullable=False)
    channel: Mapped[str] = mapped_column(String(16), nullable=False)  # web | phone | paper
    entered_by: Mapped[str] = mapped_column(String(16), nullable=False)  # self | proxy | nurse
    recorded_at: Mapped[datetime] = mapped_column(UtcDateTime, nullable=False)
    questionnaire_id: Mapped[str] = mapped_column(String(96), nullable=False)
    #: Beleg an die Patientin (advice/escalation), beim ersten Senden gespeichert (A3 T-13 F-01)
    receipt_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    #: Herkunft der Antwort: `questionnaire` (Check-in) | `free_text_followup` (Folgefrage zu einem
    #: Freitext, T-22); Regeln und Triage behandeln beide gleich, die Kennzeichnung trennt später
    source: Mapped[str] = mapped_column(
        String(24), nullable=False, default="questionnaire", server_default=text("'questionnaire'")
    )
    #: Sprache, in der gefragt wurde (bei Folgefragen die des Freitexts); sonst leer
    lang: Mapped[str | None] = mapped_column(String(8))
    #: Freitext, zu dem diese Folgefrage-Antwort gehört (kein Fremdschlüssel: Tabelle jünger)
    free_text_id: Mapped[str | None] = mapped_column(String(36), index=True)
    #: T-23: Rückblick der Fragen (NULL = unbekannt, ältere Zeilen); `lang` kommt aus T-22
    recall: Mapped[str | None] = mapped_column(String(16))  # initial_7d | daily_24h
    #: Regelauswertung: done | failed (H-5: Eingabe bleibt erhalten, T-05 zeigt "ausstehend")
    evaluation_status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="done", server_default=text("'done'")
    )
    synthetic: Mapped[bool] = _synthetic()


class Answer(WaechterBase):
    __tablename__ = "wa_answers"
    __table_args__ = (UniqueConstraint("response_id", "symptom_key", "attribute"),)

    id: Mapped[str] = _id()
    response_id: Mapped[str] = mapped_column(
        ForeignKey("wa_responses.id", ondelete="CASCADE"), nullable=False, index=True
    )
    symptom_key: Mapped[str] = mapped_column(String(64), nullable=False)
    attribute: Mapped[str] = mapped_column(String(32), nullable=False)
    #: `None` = übersprungen (fehlend, nie imputiert)
    value: Mapped[int | None] = mapped_column(Integer)
    #: T-23: Herkunft des gestellten Wortlauts: official | adapted_recall | own (NULL = unbekannt)
    wording: Mapped[str | None] = mapped_column(String(16))


class Alert(WaechterBase):
    __tablename__ = "wa_alerts"
    __table_args__ = (
        Index("ix_wa_alerts_patient_status", "patient_id", "status"),
        # R-MIS-01 (ohne Symptom): höchstens eine offene Meldung je Patientin (auch parallel)
        Index(
            "uq_wa_alert_open_patient_level",
            "patient_id",
            "rule_id",
            unique=True,
            sqlite_where=text("status = 'open' AND symptom_key = ''"),
            postgresql_where=text("status = 'open' AND symptom_key = ''"),
        ),
    )

    id: Mapped[str] = _id()
    patient_id: Mapped[str] = mapped_column(
        ForeignKey("wa_patients.id", ondelete="CASCADE"), nullable=False
    )
    response_id: Mapped[str | None] = mapped_column(ForeignKey("wa_responses.id"))
    rule_id: Mapped[str] = mapped_column(String(16), nullable=False)
    rule_version: Mapped[str] = mapped_column(String(32), nullable=False)
    level: Mapped[str] = mapped_column(String(8), nullable=False)  # red | yellow | grey
    symptom_key: Mapped[str] = mapped_column(String(64), nullable=False)
    attribute: Mapped[str | None] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="open")
    explanation_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    notified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    #: Zähler für das bedingte Update (`UPDATE … WHERE id=? AND version=?`)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, nullable=False)
    synthetic: Mapped[bool] = _synthetic()


class AlertAction(WaechterBase):
    __tablename__ = "wa_alert_actions"

    id: Mapped[str] = _id()
    alert_id: Mapped[str] = mapped_column(
        ForeignKey("wa_alerts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    action: Mapped[str] = mapped_column(String(32), nullable=False)
    decision: Mapped[str | None] = mapped_column(String(32))
    note: Mapped[str | None] = mapped_column(String(500))
    actor_user_id: Mapped[str | None] = mapped_column(String(36))
    at: Mapped[datetime] = mapped_column(UtcDateTime, nullable=False)
    synthetic: Mapped[bool] = _synthetic()


class Assessment(WaechterBase):
    __tablename__ = "wa_assessments"
    __table_args__ = (UniqueConstraint("patient_id", "client_submission_id"),)

    id: Mapped[str] = _id()
    patient_id: Mapped[str] = mapped_column(
        ForeignKey("wa_patients.id", ondelete="CASCADE"), nullable=False, index=True
    )
    assessed_at: Mapped[datetime] = mapped_column(UtcDateTime, nullable=False)
    assessed_by: Mapped[str | None] = mapped_column(String(36))
    client_submission_id: Mapped[str | None] = mapped_column(String(64))
    #: IDs der verknüpften Meldungen derselben Patientin (G-13: fremde ⇒ 422)
    related_alert_ids: Mapped[list[str]] = mapped_column(
        JSON, nullable=False, default=list, server_default=text("'[]'")
    )
    synthetic: Mapped[bool] = _synthetic()


class AssessmentItem(WaechterBase):
    __tablename__ = "wa_assessment_items"

    id: Mapped[str] = _id()
    assessment_id: Mapped[str] = mapped_column(
        ForeignKey("wa_assessments.id", ondelete="CASCADE"), nullable=False, index=True
    )
    ctcae_term_id: Mapped[str] = mapped_column(String(64), nullable=False)
    grade: Mapped[int] = mapped_column(Integer, nullable=False)  # 0 bis 5
    attribution: Mapped[str | None] = mapped_column(String(32))
    note: Mapped[str | None] = mapped_column(String(500))


class Summary(WaechterBase):
    __tablename__ = "wa_summaries"
    __table_args__ = (
        Index("uq_wa_summaries_patient_id_dedupe_key", "patient_id", "dedupe_key", unique=True),
    )

    id: Mapped[str] = _id()
    patient_id: Mapped[str] = mapped_column(
        ForeignKey("wa_patients.id", ondelete="CASCADE"), nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, nullable=False)
    generator: Mapped[str] = mapped_column(String(64), nullable=False)
    mode: Mapped[str] = mapped_column(String(16), nullable=False)
    facts_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    #: Schlüssel für die Dedupe: Fakten-Hash + Prompt-Version + angeforderter Modus
    dedupe_key: Mapped[str | None] = mapped_column(String(64))
    body_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    synthetic: Mapped[bool] = _synthetic()


class Notification(WaechterBase):
    __tablename__ = "wa_notifications"

    id: Mapped[str] = _id()
    patient_id: Mapped[str] = mapped_column(
        ForeignKey("wa_patients.id", ondelete="CASCADE"), nullable=False, index=True
    )
    alert_id: Mapped[str | None] = mapped_column(ForeignKey("wa_alerts.id"))
    level: Mapped[str] = mapped_column(String(8), nullable=False)
    channel: Mapped[str] = mapped_column(String(16), nullable=False, default="in_app")
    text: Mapped[str] = mapped_column(Text, nullable=False)
    at: Mapped[datetime] = mapped_column(UtcDateTime, nullable=False)
    synthetic: Mapped[bool] = _synthetic()


class ConfigVersion(WaechterBase):
    __tablename__ = "wa_config_versions"
    __table_args__ = (
        UniqueConstraint("kind", "version"),
        Index("uq_wa_config_active", "kind", unique=True, sqlite_where=text("active = 1")),
    )

    id: Mapped[str] = _id()
    kind: Mapped[str] = mapped_column(String(16), nullable=False)  # rules | report
    version: Mapped[str] = mapped_column(String(32), nullable=False)
    body_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, nullable=False)
    created_by: Mapped[str | None] = mapped_column(String(36))
    change_note: Mapped[str | None] = mapped_column(String(300))


class TriageDecision(WaechterBase):
    """Triage-Entscheidung je gespeicherter Antwort (triage.md §5): reine Funktion, kein LLM."""

    __tablename__ = "wa_triage_decisions"

    id: Mapped[str] = _id()
    response_id: Mapped[str] = mapped_column(
        ForeignKey("wa_responses.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    patient_id: Mapped[str] = mapped_column(
        ForeignKey("wa_patients.id", ondelete="CASCADE"), nullable=False, index=True
    )
    profile_id: Mapped[str] = mapped_column(String(64), nullable=False)
    level: Mapped[str] = mapped_column(String(8), nullable=False)  # GREEN | YELLOW | RED
    level_lo: Mapped[str] = mapped_column(String(8), nullable=False)
    level_hi: Mapped[str] = mapped_column(String(8), nullable=False)
    incomplete: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    reason_codes_json: Mapped[list[Any]] = mapped_column(JSON, nullable=False, default=list)
    rule_version: Mapped[str] = mapped_column(String(64), nullable=False)  # KB-Hash
    tree_version: Mapped[str] = mapped_column(String(64), nullable=False)
    leaf_ids_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    shield_hits_json: Mapped[list[Any]] = mapped_column(JSON, nullable=False, default=list)
    counterfactuals_json: Mapped[list[Any]] = mapped_column(JSON, nullable=False, default=list)
    recommendations_json: Mapped[list[Any]] = mapped_column(JSON, nullable=False, default=list)
    asked_questions: Mapped[int | None] = mapped_column(Integer)
    full_questions: Mapped[int | None] = mapped_column(Integer)
    # Hook H5 (Delta v2.1): Zusammensetzung (heute genau eine Komponente), nullable
    composition_hash: Mapped[str | None] = mapped_column(String(64))
    composition_status: Mapped[str | None] = mapped_column(String(16))
    component_ids_json: Mapped[list[Any] | None] = mapped_column(JSON)
    coverage_gap: Mapped[bool | None] = mapped_column(Boolean)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, nullable=False)
    synthetic: Mapped[bool] = _synthetic()


class PatientRegimen(WaechterBase):
    """Hook H5: Therapie-Zusammensetzung je Patientin, angelegt und bewusst leer (keine Module)."""

    __tablename__ = "wa_patient_regimens"

    id: Mapped[str] = _id()
    patient_id: Mapped[str] = mapped_column(
        ForeignKey("wa_patients.id", ondelete="CASCADE"), nullable=False, index=True
    )
    regimen_id: Mapped[str] = mapped_column(String(64), nullable=False)
    substances_json: Mapped[list[Any]] = mapped_column(JSON, nullable=False, default=list)
    module_ids_json: Mapped[list[Any]] = mapped_column(JSON, nullable=False, default=list)
    composition_hash: Mapped[str | None] = mapped_column(String(64))
    composition_status: Mapped[str | None] = mapped_column(String(16))
    coverage_gap: Mapped[bool | None] = mapped_column(Boolean)
    valid_from: Mapped[datetime | None] = mapped_column(UtcDateTime)
    valid_to: Mapped[datetime | None] = mapped_column(UtcDateTime)
    synthetic: Mapped[bool] = _synthetic()


class CheckinSession(WaechterBase):
    """Adaptiver Check-in (`/me/sessions`): die Schritte sind die einzige Quelle des Zustands."""

    __tablename__ = "wa_sessions"
    __table_args__ = (UniqueConstraint("patient_id", "client_session_id"),)

    id: Mapped[str] = _id()
    patient_id: Mapped[str] = mapped_column(
        ForeignKey("wa_patients.id", ondelete="CASCADE"), nullable=False, index=True
    )
    client_session_id: Mapped[str] = mapped_column(String(64), nullable=False)
    lang: Mapped[str] = mapped_column(String(8), nullable=False)
    profile_id: Mapped[str] = mapped_column(String(64), nullable=False)
    cycle_week: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    #: geordnete Liste `[symptom_key, attribute, value | null]` der bisher gestellten Fragen
    steps_json: Mapped[list[Any]] = mapped_column(JSON, nullable=False, default=list)
    status: Mapped[str] = mapped_column(String(8), nullable=False, default="open")  # open | closed
    response_id: Mapped[str | None] = mapped_column(ForeignKey("wa_responses.id"))
    stop_reason: Mapped[str | None] = mapped_column(String(16))
    stop_incomplete: Mapped[bool | None] = mapped_column(Boolean)
    #: Zähler für das bedingte Update (genau eine Antwort je Frage, auch parallel)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, nullable=False)
    synthetic: Mapped[bool] = _synthetic()


class FreeText(WaechterBase):
    """Freitext der Patientin zu einer gespeicherten Antwort (T-22, Vertrag v2.9).

    Dauerhaft: es gibt kein Löschen und keine Änderung (RESTRICT statt CASCADE). Die Vorschläge
    (`suggestions_json`) sind nur Hinweise des Adapters, geprüft durch den deterministischen
    Prüfer; sie erzeugen nie Antworten, Stufen oder Meldungen.
    """

    __tablename__ = "wa_free_texts"

    id: Mapped[str] = _id()
    patient_id: Mapped[str] = mapped_column(
        ForeignKey("wa_patients.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    response_id: Mapped[str] = mapped_column(
        ForeignKey("wa_responses.id", ondelete="RESTRICT"), nullable=False, unique=True
    )
    text: Mapped[str] = mapped_column(Text, nullable=False)
    lang: Mapped[str] = mapped_column(String(8), nullable=False)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, nullable=False)
    #: geprüfte Vorschläge `[{symptom_key, attribute | null, proposed_value | null, quote, …}]`
    suggestions_json: Mapped[list[Any]] = mapped_column(JSON, nullable=False, default=list)
    #: Adapter und Modus der Zuordnung: template | live | fallback
    mapper: Mapped[str] = mapped_column(String(64), nullable=False)
    mapper_mode: Mapped[str] = mapped_column(String(16), nullable=False)
    #: verworfene Vorschläge des Adapters (Zahl; Prüfer: Zitat nicht wörtlich, Symptom unbekannt)
    rejected_suggestions: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    synthetic: Mapped[bool] = _synthetic()


def free_text_newest_first() -> tuple[Any, ...]:
    """Sortierung "neueste zuerst": Zeitpunkt, bei Gleichstand (eingefrorene Demo-Uhr) die
    Einfügereihenfolge (`rowid`, SQLite) statt einer zufälligen id."""
    return (FreeText.created_at.desc(), literal_column("wa_free_texts.rowid").desc())


class Document(WaechterBase):
    """Hochgeladenes synthetisches Dokument mit geprüften Kandidaten (T-21, Entwurf bis Prüfung).

    Der Dokumenttext wird nicht gespeichert, nur Hash, Dateiname und die Kandidaten mit Zitat.
    `version` zählt jede Entscheidung (bedingtes Update ⇒ genau ein Erfolg je Kandidat).
    """

    __tablename__ = "wa_documents"
    __table_args__ = (UniqueConstraint("patient_id", "sha256"),)

    id: Mapped[str] = _id()
    patient_id: Mapped[str] = mapped_column(
        ForeignKey("wa_patients.id", ondelete="CASCADE"), nullable=False, index=True
    )
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    filename: Mapped[str] = mapped_column(String(120), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    extractor: Mapped[str] = mapped_column(String(80), nullable=False)
    extractor_mode: Mapped[str] = mapped_column(String(16), nullable=False)
    fallback_reason: Mapped[str | None] = mapped_column(String(32))
    candidates_json: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    rejected_json: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    uploaded_by: Mapped[str | None] = mapped_column(String(36))
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, nullable=False)
    synthetic: Mapped[bool] = _synthetic()
