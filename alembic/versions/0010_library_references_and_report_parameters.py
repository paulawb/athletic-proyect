"""persist library reference ranges and report filters

Revision ID: 0010
Revises: 0009
"""
from alembic import op
import sqlalchemy as sa

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "generated_reports",
        sa.Column("parameters", sa.JSON(), server_default=sa.text("'{}'"), nullable=False),
    )
    op.create_table(
        "library_references",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("metric", sa.String(length=80), nullable=False),
        sa.Column("unit", sa.String(length=30), nullable=False),
        sa.Column("age_range", sa.String(length=30), nullable=False),
        sa.Column("low", sa.String(length=80), nullable=False),
        sa.Column("average", sa.String(length=80), nullable=False),
        sa.Column("high", sa.String(length=80), nullable=False),
        sa.Column("source", sa.String(length=255), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    references = sa.table(
        "library_references",
        sa.column("metric", sa.String),
        sa.column("unit", sa.String),
        sa.column("age_range", sa.String),
        sa.column("low", sa.String),
        sa.column("average", sa.String),
        sa.column("high", sa.String),
        sa.column("source", sa.String),
    )
    op.bulk_insert(
        references,
        [
            {
                "metric": "Velocidad", "unit": "m/s", "age_range": "12-14",
                "low": "< 5.0", "average": "5.0-6.5", "high": "> 6.5",
                "source": "Rangos preliminares; validar con referencias normativas locales.",
            },
            {
                "metric": "Velocidad", "unit": "m/s", "age_range": "15-17",
                "low": "< 6.0", "average": "6.0-7.5", "high": "> 7.5",
                "source": "Rangos preliminares; validar con referencias normativas locales.",
            },
            {
                "metric": "Cadencia", "unit": "pasos/s", "age_range": "12-17",
                "low": "< 3.0", "average": "3.0-4.0", "high": "> 4.0",
                "source": "Rangos preliminares; validar con referencias normativas locales.",
            },
            {
                "metric": "Zancada", "unit": "m", "age_range": "12-17",
                "low": "< 1.2", "average": "1.2-1.8", "high": "> 1.8",
                "source": "Rangos preliminares; validar con referencias normativas locales.",
            },
        ],
    )


def downgrade() -> None:
    op.drop_table("library_references")
    op.drop_column("generated_reports", "parameters")
