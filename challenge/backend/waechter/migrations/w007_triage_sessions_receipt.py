"""Triage-Kern: Entscheidungen, Sitzungen, Beleg-Persistenz, Hook H5 (Zusammensetzung, leer).

Revision ID: w007
Revises: w006
"""

from typing import Any

import sqlalchemy as sa

from alembic import op
from app.persistence.models import UtcDateTime

revision = "w007"
down_revision = "w006"
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
    op.add_column("wa_responses", sa.Column("receipt_json", sa.JSON))
    op.create_table(
        "wa_triage_decisions",
        _id(),
        _fk("response_id", "wa_responses.id"),
        _fk("patient_id", "wa_patients.id"),
        sa.Column("profile_id", sa.String(64), nullable=False),
        sa.Column("level", sa.String(8), nullable=False),
        sa.Column("level_lo", sa.String(8), nullable=False),
        sa.Column("level_hi", sa.String(8), nullable=False),
        sa.Column("incomplete", sa.Boolean, nullable=False),
        sa.Column("reason_codes_json", sa.JSON, nullable=False),
        sa.Column("rule_version", sa.String(64), nullable=False),
        sa.Column("tree_version", sa.String(64), nullable=False),
        sa.Column("leaf_ids_json", sa.JSON, nullable=False),
        sa.Column("shield_hits_json", sa.JSON, nullable=False),
        sa.Column("counterfactuals_json", sa.JSON, nullable=False),
        sa.Column("recommendations_json", sa.JSON, nullable=False),
        sa.Column("asked_questions", sa.Integer),
        sa.Column("full_questions", sa.Integer),
        sa.Column("composition_hash", sa.String(64)),
        sa.Column("composition_status", sa.String(16)),
        sa.Column("component_ids_json", sa.JSON),
        sa.Column("coverage_gap", sa.Boolean),
        sa.Column("created_at", UtcDateTime, nullable=False),
        _synthetic(),
        sa.UniqueConstraint("response_id"),
    )
    op.create_index("ix_wa_triage_decisions_patient_id", "wa_triage_decisions", ["patient_id"])
    op.create_table(
        "wa_patient_regimens",
        _id(),
        _fk("patient_id", "wa_patients.id"),
        sa.Column("regimen_id", sa.String(64), nullable=False),
        sa.Column("substances_json", sa.JSON, nullable=False),
        sa.Column("module_ids_json", sa.JSON, nullable=False),
        sa.Column("composition_hash", sa.String(64)),
        sa.Column("composition_status", sa.String(16)),
        sa.Column("coverage_gap", sa.Boolean),
        sa.Column("valid_from", UtcDateTime),
        sa.Column("valid_to", UtcDateTime),
        _synthetic(),
    )
    op.create_index("ix_wa_patient_regimens_patient_id", "wa_patient_regimens", ["patient_id"])
    op.create_table(
        "wa_sessions",
        _id(),
        _fk("patient_id", "wa_patients.id"),
        sa.Column("client_session_id", sa.String(64), nullable=False),
        sa.Column("lang", sa.String(8), nullable=False),
        sa.Column("profile_id", sa.String(64), nullable=False),
        sa.Column("cycle_week", sa.Integer, nullable=False),
        sa.Column("steps_json", sa.JSON, nullable=False),
        sa.Column("status", sa.String(8), nullable=False),
        sa.Column("response_id", sa.String(36), sa.ForeignKey("wa_responses.id")),
        sa.Column("stop_reason", sa.String(16)),
        sa.Column("stop_incomplete", sa.Boolean),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column("created_at", UtcDateTime, nullable=False),
        _synthetic(),
        sa.UniqueConstraint("patient_id", "client_session_id"),
    )
    op.create_index("ix_wa_sessions_patient_id", "wa_sessions", ["patient_id"])


def downgrade() -> None:
    op.drop_index("ix_wa_sessions_patient_id", table_name="wa_sessions")
    op.drop_table("wa_sessions")
    op.drop_index("ix_wa_patient_regimens_patient_id", table_name="wa_patient_regimens")
    op.drop_table("wa_patient_regimens")
    op.drop_index("ix_wa_triage_decisions_patient_id", table_name="wa_triage_decisions")
    op.drop_table("wa_triage_decisions")
    op.drop_column("wa_responses", "receipt_json")
