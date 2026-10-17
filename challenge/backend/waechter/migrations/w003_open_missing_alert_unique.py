"""Höchstens eine offene Meldung ohne Symptom (R-MIS-01) je Patientin und Regel.

Revision ID: w003
Revises: w002
"""

import sqlalchemy as sa

from alembic import op

revision = "w003"
down_revision = "w002"
branch_labels = None
depends_on = None

_WHERE = sa.text("status = 'open' AND symptom_key = ''")


def upgrade() -> None:
    op.create_index(
        "uq_wa_alert_open_patient_level",
        "wa_alerts",
        ["patient_id", "rule_id"],
        unique=True,
        sqlite_where=_WHERE,
        postgresql_where=_WHERE,
    )


def downgrade() -> None:
    op.drop_index("uq_wa_alert_open_patient_level", table_name="wa_alerts")
