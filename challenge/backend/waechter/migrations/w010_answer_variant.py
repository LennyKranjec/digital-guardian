"""Fragevariante je Antwort (T-23, DR-041): Rückblick und Herkunft des Wortlauts.

`wa_responses.recall` (initial_7d | daily_24h) und `wa_answers.wording` (official | adapted_recall |
own) halten fest, mit welcher Variante gefragt wurde. Die Sprache `wa_responses.lang` legt T-22 in
w008 an (Absprache A1/A2). Regeln und Triage behandeln alle Varianten gleich, die Kennzeichnung
erlaubt getrennte Auswertung. Ältere Zeilen bleiben `NULL` (unbekannt).

Revision ID: w010
Revises: w007
"""

import sqlalchemy as sa

from alembic import op

revision = "w010"
down_revision = "w009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("wa_responses", sa.Column("recall", sa.String(16)))
    op.add_column("wa_answers", sa.Column("wording", sa.String(16)))


def downgrade() -> None:
    op.drop_column("wa_answers", "wording")
    op.drop_column("wa_responses", "recall")
