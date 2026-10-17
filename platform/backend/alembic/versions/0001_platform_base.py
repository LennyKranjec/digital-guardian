"""Plattform-Basis: users, auth_sessions, audit_events.

Revision ID: 0001
Revises:
"""

import sqlalchemy as sa

from alembic import op
from app.persistence.models import UtcDateTime

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("username", sa.String(64), nullable=False, unique=True),
        sa.Column("display_name", sa.String(120), nullable=False),
        sa.Column("role_name", sa.String(32), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("is_active", sa.Boolean, nullable=False),
        sa.Column("synthetic", sa.Boolean, nullable=False, server_default=sa.text("1")),
        sa.Column("created_at", UtcDateTime, nullable=False),
    )
    op.create_table(
        "auth_sessions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("created_at", UtcDateTime, nullable=False),
        sa.Column("expires_at", UtcDateTime, nullable=False),
        sa.Column("revoked_at", UtcDateTime),
    )
    op.create_index("ix_auth_sessions_user_id", "auth_sessions", ["user_id"])
    op.create_table(
        "audit_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("at", UtcDateTime, nullable=False),
        sa.Column("actor_user_id", sa.String(36)),
        sa.Column("actor_role", sa.String(32), nullable=False),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("target_type", sa.String(32), nullable=False),
        sa.Column("target_id", sa.String(64)),
        sa.Column("subject_id", sa.String(36)),
        sa.Column("details_json", sa.JSON, nullable=False),
        sa.Column("synthetic", sa.Boolean, nullable=False, server_default=sa.text("1")),
    )
    op.create_index("ix_audit_at", "audit_events", ["at"])
    op.create_index("ix_audit_subject", "audit_events", ["subject_id"])
    op.create_index("ix_audit_action", "audit_events", ["action"])


def downgrade() -> None:
    op.drop_table("audit_events")
    op.drop_table("auth_sessions")
    op.drop_table("users")
