"""Diagnose-Anpassung (v1.9): ICD-10-Code der Patientin (synthetisch) für die Fragebogenauswahl.

Revision ID: w006
Revises: w005
"""

import sqlalchemy as sa

from alembic import op

revision = "w006"
down_revision = "w005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("wa_patients", sa.Column("diagnosis_code", sa.String(16)))


def downgrade() -> None:
    op.drop_column("wa_patients", "diagnosis_code")
