"""add athlete directory fields and persisted pose keypoints

Revision ID: 0009
Revises: 0008
"""
from alembic import op
import sqlalchemy as sa

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("athletes", sa.Column("email", sa.String(length=255), nullable=True))
    op.add_column("athletes", sa.Column("category", sa.String(length=50), nullable=True))
    op.add_column("athletes", sa.Column("group_name", sa.String(length=80), nullable=True))
    op.add_column(
        "athletes",
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
    )
    op.create_index("ix_athletes_category", "athletes", ["category"])
    op.create_index("ix_athletes_group_name", "athletes", ["group_name"])
    op.add_column("frame_metrics", sa.Column("keypoints", sa.JSON(), nullable=True))
    op.add_column("generated_reports", sa.Column("downloads", sa.Integer(), server_default="0", nullable=False))


def downgrade() -> None:
    op.drop_column("frame_metrics", "keypoints")
    op.drop_column("generated_reports", "downloads")
    op.drop_index("ix_athletes_group_name", table_name="athletes")
    op.drop_index("ix_athletes_category", table_name="athletes")
    op.drop_column("athletes", "is_active")
    op.drop_column("athletes", "group_name")
    op.drop_column("athletes", "category")
    op.drop_column("athletes", "email")
