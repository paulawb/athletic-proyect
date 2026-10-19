"""move tests saved at 00:00 UTC to 12:00 UTC so they keep the chosen day in any zone

Revision ID: 0016
Revises: 0015
"""
from alembic import op

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE tests
        SET created_at = created_at + INTERVAL '12 hours'
        WHERE (created_at AT TIME ZONE 'UTC')::time = TIME '00:00:00'
        """
    )


def downgrade() -> None:
    pass
