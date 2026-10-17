"""Quittierungsnotiz (`wa_alert_actions.note`), Auswertungsstatus der Antwort (H-5).

Revision ID: w002
Revises: w001
"""

import sqlalchemy as sa

from alembic import op

revision = "w002"
down_revision = "w001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Direkte ALTER-Anweisungen (kein Batch): Batch baut die Tabelle neu auf und scheitert bei
    # aktiven Fremdschlüsseln und vorhandenen Zeilen.
    op.add_column("wa_alert_actions", sa.Column("note", sa.String(500)))
    op.add_column(
        "wa_responses",
        sa.Column(
            "evaluation_status", sa.String(16), nullable=False, server_default=sa.text("'done'")
        ),
    )


def downgrade() -> None:
    op.drop_column("wa_responses", "evaluation_status")
    op.drop_column("wa_alert_actions", "note")
