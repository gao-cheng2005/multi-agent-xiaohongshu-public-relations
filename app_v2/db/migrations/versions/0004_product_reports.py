"""add product_reports

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-21
"""
from alembic import op
import sqlalchemy as sa

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """新增产品优化建议缓存表。"""
    op.create_table(
        "product_reports",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("brand_id", sa.Uuid(), nullable=False),
        sa.Column("product", sa.String(length=200), nullable=False),
        sa.Column("report", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_product_reports_product", "product_reports", ["product"], unique=True)


def downgrade() -> None:
    """回退：删除产品报告缓存表和它的索引。"""
    op.drop_index("ix_product_reports_product", table_name="product_reports")
    op.drop_table("product_reports")
