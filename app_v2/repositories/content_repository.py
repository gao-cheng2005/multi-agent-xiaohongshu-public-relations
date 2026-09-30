"""笔记与评论表数据读写。

这个文件负责"笔记"和"评论"两张表的所有数据库操作：
- 笔记：按编号/去重指纹查找、新建或更新、列出最近的笔记；
- 评论：新增、按评论编号查重、列出某篇笔记的全部评论。
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Comment, Content


class ContentRepository:
    """笔记和评论表的数据库操作集合。"""

    async def get_by_external_id(self, session: AsyncSession, content_id: str) -> Content | None:
        """按平台笔记编号查找一条笔记。"""
        result = await session.execute(select(Content).where(Content.content_id == content_id))
        return result.scalar_one_or_none()

    async def get_by_dedup_hash(self, session: AsyncSession, dedup_hash: str) -> Content | None:
        """按去重指纹查找一条笔记。

        指纹相同的两条链接（只是参数不同）其实是同一篇，用指纹能识别出来。
        """
        result = await session.execute(select(Content).where(Content.dedup_hash == dedup_hash))
        return result.scalar_one_or_none()

    async def create_or_update(
        self, session: AsyncSession, brand_id: uuid.UUID, payload: dict
    ) -> Content:
        """新建笔记；同一篇已存在则只更新会变化的字段，不重复插入。"""
        instance = await self.get_by_dedup_hash(session, payload["dedup_hash"])
        if instance is None:
            instance = Content(brand_id=brand_id, **payload)
            session.add(instance)
        else:
            # 只覆盖来源、关键词、互动数这些容易变化的字段
            for field in (
                "source_type", "keyword", "like_count", "collect_count",
                "comment_count", "share_count", "view_count",
            ):
                if field in payload:
                    setattr(instance, field, payload[field])
        await session.flush()
        return instance

    async def list_with_latest_analysis(self, session: AsyncSession, limit: int) -> list[Content]:
        """列出最近的若干条笔记（新的在前）。"""
        result = await session.execute(
            select(Content).order_by(Content.created_at.desc()).limit(limit)
        )
        return list(result.scalars().all())

    async def add_comment(
        self, session: AsyncSession, brand_id: uuid.UUID, payload: dict
    ) -> Comment:
        """新增一条评论记录。"""
        instance = Comment(brand_id=brand_id, **payload)
        session.add(instance)
        await session.flush()
        return instance

    async def get_comment(
        self, session: AsyncSession, note_id: str, comment_id: str
    ) -> Comment | None:
        """按（笔记编号 + 评论编号）查一条评论，用于去重。"""
        result = await session.execute(
            select(Comment).where(Comment.note_id == note_id, Comment.comment_id == comment_id)
        )
        return result.scalar_one_or_none()

    async def list_comments(self, session: AsyncSession, note_id: str) -> list[Comment]:
        """列出某篇笔记的全部评论，按存储先后排列。"""
        result = await session.execute(
            select(Comment).where(Comment.note_id == note_id).order_by(Comment.created_at)
        )
        return list(result.scalars().all())
