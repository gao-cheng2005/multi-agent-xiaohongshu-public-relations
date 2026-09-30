"""问题标签表数据读写与聚合统计。

"问题标签"是从笔记和评论里抽取出来的用户问题（如"做工/材质""发热/散热"），
用于产品维度分析。这个文件负责标签表的所有数据库操作，以及按产品聚合统计。

聚合口径比较复杂：正文每条算 1 次，评论按不同用户去重（同一用户多条算 1 次）。
"""

from __future__ import annotations

import uuid

from sqlalchemy import case, delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import IssueTag
from ..services.agents.prompts import normalize_dimension_name


class IssueTagRepository:
    """问题标签表的数据库操作集合。"""

    async def replace_for_content(
        self,
        session: AsyncSession,
        brand_id: uuid.UUID,
        product: str,
        content_id: str,
        items: list[dict],
    ) -> int:
        """把一篇笔记的问题标签整批覆盖写入（先删旧再写新，保证幂等）。"""
        await session.execute(delete(IssueTag).where(IssueTag.content_id == content_id))
        written = 0
        for item in items:
            # 别名归一化；维度名为空则跳过，避免落成"其他问题"这类无意义桶
            dimension = normalize_dimension_name(item.get("dimension", ""))
            if not dimension:
                continue
            session.add(
                IssueTag(
                    brand_id=brand_id,
                    product=product,
                    content_id=content_id,
                    dimension=dimension,
                    dimension_def=item.get("dimension_def", ""),
                    label=item.get("label", ""),
                    polarity=item.get("polarity", "negative"),
                    source=item.get("source", "comment"),
                    author=item.get("author", ""),
                    excerpt=item.get("excerpt", ""),
                    confirmed=item.get("confirmed", False),
                )
            )
            written += 1
        await session.flush()
        return written

    async def list_labels(self, session: AsyncSession) -> list[str]:
        """列出所有问题标签的"用户原话"，供词频统计用。"""
        result = await session.execute(select(IssueTag.label))
        return [r[0] for r in result.all()]

    async def list_dimensions_by_content(self, session: AsyncSession, content_id: str) -> list[str]:
        """列出某篇笔记的问题维度（去重、排序），供文案检索用。"""
        result = await session.execute(
            select(IssueTag.dimension).where(IssueTag.content_id == content_id)
        )
        dims = [r[0] for r in result.all() if r[0]]
        return sorted(set(dims))

    async def aggregate_by_product(self, session: AsyncSession, product: str) -> dict:
        """按产品聚合问题维度。

        统计口径：正文每条算 1 次；评论按不同用户去重（同一用户多条只算 1 次）。
        结果包含每个维度的出现次数、负面次数、常见说法和一条样例摘录。
        """
        result = await session.execute(
            select(
                IssueTag.dimension,
                # 同一维度不同定义文本不拆行，只取任一条
                func.max(IssueTag.dimension_def).label("dimension_def"),
                # 出现（主体）次数 = 正文条数 + 评论不同作者数
                (
                    func.sum(case((IssueTag.source == "note", 1), else_=0))
                    + func.count(
                        func.distinct(
                            func.if_(IssueTag.source == "comment", IssueTag.author, None)
                        )
                    )
                ).label("cnt"),
                # 负面（主体）次数同理
                (
                    func.sum(
                        case(
                            ((IssueTag.source == "note") & (IssueTag.polarity == "negative"), 1),
                            else_=0,
                        )
                    )
                    + func.count(
                        func.distinct(
                            func.if_(
                                (IssueTag.source == "comment") & (IssueTag.polarity == "negative"),
                                IssueTag.author,
                                None,
                            )
                        )
                    )
                ).label("neg"),
                func.count(func.distinct(IssueTag.label)).label("label_cnt"),
            )
            .where(IssueTag.product == product, IssueTag.confirmed.is_(True))
            .group_by(IssueTag.dimension)
            .order_by(func.count().desc())
        )

        dims = [
            {
                "dimension": row.dimension,
                "dimension_def": row.dimension_def,
                "count": row.cnt,
                "negative": row.neg,
                "label_count": row.label_cnt,
                "labels": [],
                "sample_excerpt": "",
            }
            for row in result
        ]

        # 为每个维度补上"常见说法（前 5）"和"一条样例摘录"
        for d in dims:
            label_rows = await session.execute(
                select(IssueTag.label)
                .where(
                    IssueTag.product == product,
                    IssueTag.confirmed.is_(True),
                    IssueTag.dimension == d["dimension"],
                )
                .distinct()
                .limit(5)
            )
            d["labels"] = [r[0] for r in label_rows.all() if r[0]]

            excerpt = await session.execute(
                select(IssueTag.excerpt)
                .where(
                    IssueTag.product == product,
                    IssueTag.confirmed.is_(True),
                    IssueTag.dimension == d["dimension"],
                    IssueTag.excerpt != "",
                )
                .limit(1)
            )
            d["sample_excerpt"] = (excerpt.scalar() or "")[:80]

        return {"product": product, "dimensions": dims}

    async def unconfirmed_dimensions(
        self, session: AsyncSession, product: str | None = None
    ) -> list[dict]:
        """列出待确认（智能体新建）的维度及它们被提到的次数。"""
        stmt = (
            select(IssueTag.dimension, IssueTag.dimension_def, func.count().label("cnt"))
            .where(IssueTag.confirmed.is_(False))
        )
        if product:
            stmt = stmt.where(IssueTag.product == product)
        stmt = stmt.group_by(IssueTag.dimension, IssueTag.dimension_def).order_by(func.count().desc())
        result = await session.execute(stmt)
        return [
            {"dimension": r.dimension, "dimension_def": r.dimension_def, "count": r.cnt}
            for r in result
        ]

    async def set_confirmed(
        self, session: AsyncSession, dimension: str, confirmed: bool = True, product: str | None = None
    ) -> int:
        """确认（或忽略）一个待确认维度。"""
        stmt = update(IssueTag).where(IssueTag.dimension == dimension).values(confirmed=confirmed)
        if product:
            stmt = stmt.where(IssueTag.product == product)
        result = await session.execute(stmt)
        return result.rowcount or 0

    async def rename_dimension(self, session: AsyncSession, from_dim: str, into_dim: str) -> int:
        """把 from_dim 的全部标签改名为 into_dim（维度归并用）。"""
        result = await session.execute(
            update(IssueTag)
            .where(IssueTag.dimension == from_dim)
            .values(dimension=into_dim, confirmed=True)
        )
        return result.rowcount or 0
