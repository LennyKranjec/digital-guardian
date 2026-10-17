"""Einschreibung durch das Personal (T-34): Idempotenzschlüssel je angelegter Patientin.

Revision ID: w011
Revises: w010
"""

import sqlalchemy as sa

from alembic import op

revision = "w011"
down_revision = "w010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("wa_patients", sa.Column("enrollment_request_id", sa.String(64)))
    op.create_index(
        "ix_wa_patients_enrollment_request_id",
        "wa_patients",
        ["enrollment_request_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_wa_patients_enrollment_request_id", table_name="wa_patients")
    op.drop_column("wa_patients", "enrollment_request_id")
