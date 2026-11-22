"""persist estimated total steps for each analysis

Revision ID: 0018
Revises: 0017
"""
import sqlalchemy as sa
from alembic import op

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("metrics", sa.Column("step_count", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("metrics", "step_count")
