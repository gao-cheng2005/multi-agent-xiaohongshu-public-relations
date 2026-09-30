"""add issue_tags.author

Revision ID: 0005
Revises: 0004
Create Date: 2026-09-21
"""
from alembic import op
import sqlalchemy as sa

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """新增提出者昵称列（主体去重计次用）。"""
    op.add_column("issue_tags", sa.Column("author", sa.String(length=200), nullable=False, server_default=""))


def downgrade() -> None:
    """回退：删除 author（提出者昵称）这一列。"""
    op.drop_column("issue_tags", "author")
