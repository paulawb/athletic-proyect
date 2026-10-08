"""scope athlete data to accounts and retain generated report files

Revision ID: 0014
Revises: 0013
"""
from alembic import op
import sqlalchemy as sa


revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "athletes",
        sa.Column("owner_user_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_athletes_owner_user_id_users",
        "athletes",
        "users",
        ["owner_user_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index("ix_athletes_owner_user_id", "athletes", ["owner_user_id"])
    op.drop_index("ix_athletes_identification", table_name="athletes")
    op.create_unique_constraint(
        "uq_athletes_owner_identification",
        "athletes",
        ["owner_user_id", "identification"],
    )

    op.add_column(
        "generated_reports",
        sa.Column("file_content", sa.LargeBinary(), nullable=True),
    )

    op.execute("UPDATE users SET role = 'docente' WHERE role = 'estudiante'")
    op.drop_constraint("ck_users_role", "users", type_="check")
    op.create_check_constraint("ck_users_role", "users", "role = 'docente'")
    op.execute("DELETE FROM settings WHERE section = 'institution'")


def downgrade() -> None:
    op.drop_constraint("ck_users_role", "users", type_="check")
    op.create_check_constraint("ck_users_role", "users", "role IN ('docente', 'estudiante')")
    op.drop_column("generated_reports", "file_content")
    op.drop_constraint("uq_athletes_owner_identification", "athletes", type_="unique")
    op.create_index("ix_athletes_identification", "athletes", ["identification"], unique=True)
    op.drop_index("ix_athletes_owner_user_id", table_name="athletes")
    op.drop_constraint("fk_athletes_owner_user_id_users", "athletes", type_="foreignkey")
    op.drop_column("athletes", "owner_user_id")
