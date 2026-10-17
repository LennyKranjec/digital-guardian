"""Freitext der Patientin (T-22): Tabelle `wa_free_texts`, Herkunft der Antwort (`source`, `lang`).

Revision ID: w008
Revises: w007
"""

from typing import Any

import sqlalchemy as sa

from alembic import op
from app.persistence.models import UtcDateTime

revision = "w008"
down_revision = "w007"
branch_labels = None
depends_on = None


def _fk(name: str, target: str, *, unique: bool = False) -> sa.Column[Any]:
    return sa.Column(
        name,
        sa.String(36),
        sa.ForeignKey(target, ondelete="RESTRICT"),
        nullable=False,
        unique=unique,
    )


def upgrade() -> None:
    op.add_column(
        "wa_responses",
        sa.Column("source", sa.String(24), nullable=False, server_default="questionnaire"),
    )
    op.add_column("wa_responses", sa.Column("lang", sa.String(8)))
    op.add_column("wa_responses", sa.Column("free_text_id", sa.String(36)))
    op.create_index("ix_wa_responses_free_text_id", "wa_responses", ["free_text_id"])
    op.create_table(
        "wa_free_texts",
        sa.Column("id", sa.String(36), primary_key=True),
        _fk("patient_id", "wa_patients.id"),
        _fk("response_id", "wa_responses.id", unique=True),
        sa.Column("text", sa.Text, nullable=False),
        sa.Column("lang", sa.String(8), nullable=False),
        sa.Column("created_at", UtcDateTime, nullable=False),
        sa.Column("suggestions_json", sa.JSON, nullable=False),
        sa.Column("mapper", sa.String(64), nullable=False),
        sa.Column("mapper_mode", sa.String(16), nullable=False),
        sa.Column("rejected_suggestions", sa.Integer, nullable=False, server_default="0"),
        sa.Column("synthetic", sa.Boolean, nullable=False, server_default=sa.text("1")),
    )
    op.create_index("ix_wa_free_texts_patient_id", "wa_free_texts", ["patient_id"])


def downgrade() -> None:
    op.drop_index("ix_wa_responses_free_text_id", table_name="wa_responses")
    op.drop_column("wa_responses", "free_text_id")
    op.drop_column("wa_responses", "lang")
    op.drop_column("wa_responses", "source")
    op.drop_index("ix_wa_free_texts_patient_id", table_name="wa_free_texts")
    op.drop_table("wa_free_texts")
