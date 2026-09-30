"""add response_plans.channel

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-19
"""
from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """新增 channel 字段，记录 Agent③ 的渠道结论（dm/public/skip）。"""
    op.add_column("response_plans", sa.Column("channel", sa.String(20), nullable=True))


def downgrade() -> None:
    """回退：删除 channel 字段。"""
    op.drop_column("response_plans", "channel")