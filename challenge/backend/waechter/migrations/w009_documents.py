"""Dokumente ⇒ FHIR (T-21): `wa_documents` mit Kandidaten, Verwerfungen und Versionszähler.

Revision ID: w009
Revises: w008  (Kette w007 → w008 (T-22) → w009 → w010)
"""

import sqlalchemy as sa

from alembic import op
from app.persistence.models import UtcDateTime

revision = "w009"
down_revision = "w008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "wa_documents",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "patient_id",
            sa.String(36),
            sa.ForeignKey("wa_patients.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("filename", sa.String(120), nullable=False),
        sa.Column("size_bytes", sa.Integer, nullable=False),
        sa.Column("extractor", sa.String(80), nullable=False),
        sa.Column("extractor_mode", sa.String(16), nullable=False),
        sa.Column("fallback_reason", sa.String(32)),
        sa.Column("candidates_json", sa.JSON, nullable=False),
        sa.Column("rejected_json", sa.JSON, nullable=False),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column("uploaded_by", sa.String(36)),
        sa.Column("created_at", UtcDateTime, nullable=False),
        sa.Column("synthetic", sa.Boolean, nullable=False, server_default=sa.text("1")),
        sa.UniqueConstraint("patient_id", "sha256"),
    )
    op.create_index("ix_wa_documents_patient_id", "wa_documents", ["patient_id"])


def downgrade() -> None:
    op.drop_index("ix_wa_documents_patient_id", table_name="wa_documents")
    op.drop_table("wa_documents")
