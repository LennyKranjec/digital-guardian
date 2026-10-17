"""KI-Kurzfassung: Dedupe-Schlüssel je Patientin (gleicher Schlüssel ⇒ dieselbe Zusammenfassung).

Revision ID: w005
Revises: w004
"""

import sqlalchemy as sa

from alembic import op

revision = "w005"
down_revision = "w004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("wa_summaries", sa.Column("dedupe_key", sa.String(64)))
    op.create_index(
        "uq_wa_summaries_patient_id_dedupe_key",
        "wa_summaries",
        ["patient_id", "dedupe_key"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_wa_summaries_patient_id_dedupe_key", table_name="wa_summaries")
    op.drop_column("wa_summaries", "dedupe_key")
