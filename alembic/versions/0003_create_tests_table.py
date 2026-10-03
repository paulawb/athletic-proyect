"""create tests table

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-09
"""
from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tests",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "athlete_id",
            sa.Integer(),
            sa.ForeignKey("athletes.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("distance", sa.Integer(), nullable=False),
        sa.Column("test_type", sa.String(length=50), nullable=False),
        sa.Column("technique", sa.String(length=50), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="PENDING"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_tests_athlete_id", "tests", ["athlete_id"])


def downgrade() -> None:
    op.drop_index("ix_tests_athlete_id", table_name="tests")
    op.drop_table("tests")
