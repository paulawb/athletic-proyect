"""add indexes and constraints for performance (Fase 12)

Revision ID: 0007
Revises: 0006
Create Date: 2026-09-30
"""
from alembic import op
import sqlalchemy as sa

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # analyses.status: ya tiene index=True en el modelo, pero el schema
    # antiguo (0005) no lo creó. Lo añadimos explicitamente.
    op.create_index("ix_analyses_status", "analyses", ["status"])
    # Composite index used by GenerateAnalysisReport._build_comparison:
    #   "latest COMPLETED analysis for a video"
    op.create_index(
        "ix_analyses_video_completed", "analyses", ["video_id", "completed_at"]
    )
    # completed_at solo: filtra ORDER BY completed_at DESC en list_analyses.
    op.create_index("ix_analyses_completed_at", "analyses", ["completed_at"])


def downgrade() -> None:
    op.drop_index("ix_analyses_completed_at", table_name="analyses")
    op.drop_index("ix_analyses_video_completed", table_name="analyses")
    op.drop_index("ix_analyses_status", table_name="analyses")