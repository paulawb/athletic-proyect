"""create metrics and frame_metrics tables

Revision ID: 0006
Revises: 0005
Create Date: 2026-09-16
"""
from alembic import op
import sqlalchemy as sa

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "metrics",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "analysis_id",
            sa.Integer(),
            sa.ForeignKey("analyses.id", ondelete="RESTRICT"),
            nullable=False,
            unique=True,
        ),
        sa.Column("average_speed", sa.Float(), nullable=False),
        sa.Column("maximum_speed", sa.Float(), nullable=False),
        sa.Column("stride_length", sa.Float(), nullable=False),
        sa.Column("cadence", sa.Float(), nullable=False),
        sa.Column("posture_score", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_metrics_analysis_id", "metrics", ["analysis_id"], unique=True)

    op.create_table(
        "frame_metrics",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "analysis_id",
            sa.Integer(),
            sa.ForeignKey("analyses.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("frame_number", sa.Integer(), nullable=False),
        sa.Column("timestamp", sa.Float(), nullable=False),
        sa.Column("x_position", sa.Float(), nullable=False),
        sa.Column("y_position", sa.Float(), nullable=False),
        sa.Column("speed", sa.Float(), nullable=False),
        sa.Column("stride_phase", sa.String(length=20), nullable=False),
        sa.Column("posture_score", sa.Float(), nullable=False),
    )
    op.create_index("ix_frame_metrics_analysis_id", "frame_metrics", ["analysis_id"])


def downgrade() -> None:
    op.drop_index("ix_frame_metrics_analysis_id", table_name="frame_metrics")
    op.drop_table("frame_metrics")
    op.drop_index("ix_metrics_analysis_id", table_name="metrics")
    op.drop_table("metrics")
