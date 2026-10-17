"""Wächter-Basis: Tabellen `wa_*` (Patient:innen, Therapien, Antworten, Meldungen, Konfiguration).

Revision ID: w001
Revises: 0001
"""

from typing import Any

import sqlalchemy as sa

from alembic import op
from app.persistence.models import UtcDateTime

revision = "w001"
down_revision = "0001"
branch_labels = None
depends_on = None


def _id() -> sa.Column[Any]:
    return sa.Column("id", sa.String(36), primary_key=True)


def _synthetic() -> sa.Column[Any]:
    return sa.Column("synthetic", sa.Boolean, nullable=False, server_default=sa.text("1"))


def _fk(name: str, target: str, *, nullable: bool = False, cascade: bool = True) -> sa.Column[Any]:
    return sa.Column(
        name,
        sa.String(36),
        sa.ForeignKey(target, ondelete="CASCADE" if cascade else None),
        nullable=nullable,
    )


def upgrade() -> None:
    op.create_table(
        "wa_patients",
        _id(),
        sa.Column("pseudonym", sa.String(16), nullable=False, unique=True),
        sa.Column("display_name", sa.String(120), nullable=False),
        sa.Column("birth_year", sa.Integer, nullable=False),
        sa.Column("sex", sa.String(16), nullable=False),
        sa.Column("language", sa.String(8), nullable=False),
        sa.Column("diagnosis_text", sa.Text),
        sa.Column("user_id", sa.String(36), unique=True),
        _synthetic(),
    )
    op.create_table(
        "wa_therapies",
        _id(),
        _fk("patient_id", "wa_patients.id"),
        sa.Column("regimen_id", sa.String(64), nullable=False),
        sa.Column("cycle_start", UtcDateTime, nullable=False),
        _synthetic(),
    )
    op.create_index("ix_wa_therapies_patient_id", "wa_therapies", ["patient_id"])
    op.create_table(
        "wa_visits",
        _id(),
        _fk("patient_id", "wa_patients.id"),
        sa.Column("at", UtcDateTime, nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        _synthetic(),
    )
    op.create_index("ix_wa_visits_patient_id", "wa_visits", ["patient_id"])
    op.create_table(
        "wa_responses",
        _id(),
        _fk("patient_id", "wa_patients.id"),
        sa.Column("client_submission_id", sa.String(64), nullable=False),
        sa.Column("channel", sa.String(16), nullable=False),
        sa.Column("entered_by", sa.String(16), nullable=False),
        sa.Column("recorded_at", UtcDateTime, nullable=False),
        sa.Column("questionnaire_id", sa.String(96), nullable=False),
        _synthetic(),
        sa.UniqueConstraint("patient_id", "client_submission_id"),
    )
    op.create_index("ix_wa_responses_patient_at", "wa_responses", ["patient_id", "recorded_at"])
    op.create_table(
        "wa_answers",
        _id(),
        _fk("response_id", "wa_responses.id"),
        sa.Column("symptom_key", sa.String(64), nullable=False),
        sa.Column("attribute", sa.String(32), nullable=False),
        sa.Column("value", sa.Integer),
        sa.UniqueConstraint("response_id", "symptom_key", "attribute"),
    )
    op.create_index("ix_wa_answers_response_id", "wa_answers", ["response_id"])
    op.create_table(
        "wa_alerts",
        _id(),
        _fk("patient_id", "wa_patients.id"),
        _fk("response_id", "wa_responses.id", nullable=True, cascade=False),
        sa.Column("rule_id", sa.String(16), nullable=False),
        sa.Column("rule_version", sa.String(32), nullable=False),
        sa.Column("level", sa.String(8), nullable=False),
        sa.Column("symptom_key", sa.String(64), nullable=False),
        sa.Column("attribute", sa.String(32)),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("explanation_json", sa.JSON, nullable=False),
        sa.Column("notified", sa.Boolean, nullable=False),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column("created_at", UtcDateTime, nullable=False),
        _synthetic(),
    )
    op.create_index("ix_wa_alerts_patient_status", "wa_alerts", ["patient_id", "status"])
    op.create_table(
        "wa_alert_actions",
        _id(),
        _fk("alert_id", "wa_alerts.id"),
        sa.Column("action", sa.String(32), nullable=False),
        sa.Column("decision", sa.String(32)),
        sa.Column("actor_user_id", sa.String(36)),
        sa.Column("at", UtcDateTime, nullable=False),
        _synthetic(),
    )
    op.create_index("ix_wa_alert_actions_alert_id", "wa_alert_actions", ["alert_id"])
    op.create_table(
        "wa_assessments",
        _id(),
        _fk("patient_id", "wa_patients.id"),
        sa.Column("assessed_at", UtcDateTime, nullable=False),
        sa.Column("assessed_by", sa.String(36)),
        sa.Column("client_submission_id", sa.String(64)),
        _synthetic(),
        sa.UniqueConstraint("patient_id", "client_submission_id"),
    )
    op.create_index("ix_wa_assessments_patient_id", "wa_assessments", ["patient_id"])
    op.create_table(
        "wa_assessment_items",
        _id(),
        _fk("assessment_id", "wa_assessments.id"),
        sa.Column("ctcae_term_id", sa.String(64), nullable=False),
        sa.Column("grade", sa.Integer, nullable=False),
        sa.Column("attribution", sa.String(32)),
    )
    op.create_index(
        "ix_wa_assessment_items_assessment_id", "wa_assessment_items", ["assessment_id"]
    )
    op.create_table(
        "wa_summaries",
        _id(),
        _fk("patient_id", "wa_patients.id"),
        sa.Column("created_at", UtcDateTime, nullable=False),
        sa.Column("generator", sa.String(64), nullable=False),
        sa.Column("mode", sa.String(16), nullable=False),
        sa.Column("facts_hash", sa.String(64), nullable=False),
        sa.Column("body_json", sa.JSON, nullable=False),
        _synthetic(),
    )
    op.create_index("ix_wa_summaries_patient_id", "wa_summaries", ["patient_id"])
    op.create_table(
        "wa_notifications",
        _id(),
        _fk("patient_id", "wa_patients.id"),
        _fk("alert_id", "wa_alerts.id", nullable=True, cascade=False),
        sa.Column("level", sa.String(8), nullable=False),
        sa.Column("channel", sa.String(16), nullable=False),
        sa.Column("text", sa.Text, nullable=False),
        sa.Column("at", UtcDateTime, nullable=False),
        _synthetic(),
    )
    op.create_index("ix_wa_notifications_patient_id", "wa_notifications", ["patient_id"])
    op.create_table(
        "wa_config_versions",
        _id(),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("version", sa.String(32), nullable=False),
        sa.Column("body_json", sa.JSON, nullable=False),
        sa.Column("active", sa.Boolean, nullable=False),
        sa.Column("created_at", UtcDateTime, nullable=False),
        sa.Column("created_by", sa.String(36)),
        sa.Column("change_note", sa.String(300)),
        sa.UniqueConstraint("kind", "version"),
    )
    op.create_index(
        "uq_wa_config_active",
        "wa_config_versions",
        ["kind"],
        unique=True,
        sqlite_where=sa.text("active = 1"),
    )


def downgrade() -> None:
    for table in (
        "wa_config_versions",
        "wa_notifications",
        "wa_summaries",
        "wa_assessment_items",
        "wa_assessments",
        "wa_alert_actions",
        "wa_alerts",
        "wa_answers",
        "wa_responses",
        "wa_visits",
        "wa_therapies",
        "wa_patients",
    ):
        op.drop_table(table)
