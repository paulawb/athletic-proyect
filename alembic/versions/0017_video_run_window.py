"""add optional run start/end seconds to videos

Revision ID: 0017
Revises: 0016
"""
import sqlalchemy as sa
from alembic import op

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("videos", sa.Column("run_start_s", sa.Float(), nullable=True))
    op.add_column("videos", sa.Column("run_end_s", sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column("videos", "run_end_s")
    op.drop_column("videos", "run_start_s")
