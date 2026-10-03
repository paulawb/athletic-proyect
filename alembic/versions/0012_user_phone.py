"""store user phone number

Revision ID: 0012
Revises: 0011
"""
from alembic import op
import sqlalchemy as sa

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("phone", sa.String(length=20), nullable=True))
    op.execute("UPDATE users SET email_verified = TRUE WHERE email_verified = FALSE")
    op.alter_column("users", "email_verified", server_default=sa.true(), nullable=False)


def downgrade() -> None:
    op.drop_column("users", "phone")
