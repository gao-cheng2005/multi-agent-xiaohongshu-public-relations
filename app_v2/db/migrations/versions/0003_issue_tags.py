"""add issue_tags

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-19
"""
from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """新增问题标签表（产品数据分析用）。"""
    op.create_table(
        "issue_tags",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("brand_id", sa.Uuid(), nullable=False),
        sa.Column("product", sa.String(length=200), nullable=False),
        sa.Column("content_id", sa.String(length=200), nullable=False),
        sa.Column("dimension", sa.String(length=100), nullable=False),
        sa.Column("dimension_def", sa.String(length=500), nullable=False),
        sa.Column("label", sa.String(length=200), nullable=False),
        sa.Column("polarity", sa.String(length=20), nullable=False),
        sa.Column("source", sa.String(length=20), nullable=False),
        sa.Column("excerpt", sa.Text(), nullable=False),
        sa.Column("confirmed", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_issue_tags_content_id", "issue_tags", ["content_id"])
    op.create_index("ix_issue_tags_dimension", "issue_tags", ["dimension"])
    op.create_index("ix_issue_tags_product", "issue_tags", ["product"])


def downgrade() -> None:
    """回退：删除问题标签表。"""
    op.drop_index("ix_issue_tags_product", table_name="issue_tags")
    op.drop_index("ix_issue_tags_dimension", table_name="issue_tags")
    op.drop_index("ix_issue_tags_content_id", table_name="issue_tags")
    op.drop_table("issue_tags")
