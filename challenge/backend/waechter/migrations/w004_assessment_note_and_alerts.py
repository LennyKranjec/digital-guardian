"""Arztaufnahme: Notiz je Begriff und verknüpfte Meldungen.

Revision ID: w004
Revises: w003
"""

import sqlalchemy as sa

from alembic import op

revision = "w004"
down_revision = "w003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("wa_assessment_items", sa.Column("note", sa.String(500)))
    op.add_column(
        "wa_assessments",
        sa.Column("related_alert_ids", sa.JSON, nullable=False, server_default=sa.text("'[]'")),
    )


def downgrade() -> None:
    op.drop_column("wa_assessments", "related_alert_ids")
    op.drop_column("wa_assessment_items", "note")
