"""Add agent_tier_assignments table.

Revision ID: 001_add_agent_tier_assignments
Revises:
Create Date: 2026-03-05 00:00:00.000000

Constitutional Hash: cdd01ef066bc6cf2
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "001_add_agent_tier_assignments"
down_revision: str | None = None
branch_labels: str | tuple[str, ...] | None = None
depends_on: str | tuple[str, ...] | None = None


def upgrade() -> None:
    op.create_table(
        "agent_tier_assignments",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
        ),
        sa.Column("agent_id", sa.String(), nullable=False),
        sa.Column("tenant_id", sa.String(), nullable=False),
        sa.Column("tier", sa.String(), nullable=False),
        sa.Column("action_boundaries", postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column("assigned_by", sa.String(), nullable=False),
        sa.Column(
            "assigned_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "agent_id",
            name="uq_agent_tier_assignments_tenant_agent",
        ),
    )
    op.create_index(
        "ix_agent_tier_assignments_agent_id",
        "agent_tier_assignments",
        ["agent_id"],
        unique=False,
    )
    op.create_index(
        "ix_agent_tier_assignments_tenant_id",
        "agent_tier_assignments",
        ["tenant_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_agent_tier_assignments_tenant_id", table_name="agent_tier_assignments")
    op.drop_index("ix_agent_tier_assignments_agent_id", table_name="agent_tier_assignments")
    op.drop_table("agent_tier_assignments")
