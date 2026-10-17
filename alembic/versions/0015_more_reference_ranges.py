"""add orientative reference ranges for all age groups

Revision ID: 0015
Revises: 0014
"""
from alembic import op
import sqlalchemy as sa

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None

_SOURCE = (
    "Rango orientativo para pruebas cortas de velocidad (10-30 m); "
    "validar con referencias normativas locales."
)
_POSTURE_SOURCE = "Niveles usados por el software: >= 80 % adecuada, 60-80 % media, < 60 % baja."

# (metrica, unidad, edades, bajo, promedio, alto)
_ROWS = [
    ("Velocidad", "m/s", "6-11", "< 3.5", "3.5-5.0", "> 5.0"),
    ("Cadencia", "pasos/s", "6-11", "< 3.2", "3.2-4.2", "> 4.2"),
    ("Zancada", "m", "6-11", "< 0.8", "0.8-1.3", "> 1.3"),
    ("Velocidad", "m/s", "18-25", "< 6.0", "6.0-7.5", "> 7.5"),
    ("Cadencia", "pasos/s", "18-25", "< 3.5", "3.5-4.5", "> 4.5"),
    ("Zancada", "m", "18-25", "< 1.5", "1.5-2.2", "> 2.2"),
    ("Velocidad", "m/s", "26-35", "< 5.5", "5.5-7.0", "> 7.0"),
    ("Cadencia", "pasos/s", "26-35", "< 3.3", "3.3-4.3", "> 4.3"),
    ("Zancada", "m", "26-35", "< 1.4", "1.4-2.1", "> 2.1"),
    ("Velocidad", "m/s", "36-45", "< 5.0", "5.0-6.5", "> 6.5"),
    ("Cadencia", "pasos/s", "36-45", "< 3.0", "3.0-4.0", "> 4.0"),
    ("Zancada", "m", "36-45", "< 1.3", "1.3-2.0", "> 2.0"),
    ("Velocidad", "m/s", "46+", "< 4.0", "4.0-5.5", "> 5.5"),
    ("Cadencia", "pasos/s", "46+", "< 2.8", "2.8-3.8", "> 3.8"),
    ("Zancada", "m", "46+", "< 1.1", "1.1-1.8", "> 1.8"),
]


def upgrade() -> None:
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
    rows = [
        {"metric": m, "unit": u, "age_range": a, "low": lo, "average": av, "high": hi, "source": _SOURCE}
        for m, u, a, lo, av, hi in _ROWS
    ]
    rows.append(
        {
            "metric": "Postura", "unit": "%", "age_range": "Todas las edades",
            "low": "< 60", "average": "60-80", "high": "> 80", "source": _POSTURE_SOURCE,
        }
    )
    op.bulk_insert(references, rows)


def downgrade() -> None:
    op.execute(
        "DELETE FROM library_references WHERE age_range IN ('6-11','18-25','26-35','36-45','46+','Todas las edades')"
    )
