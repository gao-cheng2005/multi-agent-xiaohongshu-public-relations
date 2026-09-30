"""
scripts/rebuild_plan_copy_index 文案话术库全量重建脚本。

把历史已 closed 且带实际文案（channel∈dm/public、文案非空）的方案全部重新灌入向量库。
用于首次启用 RAG、向量库损坏或数据修复时兜底。

用法（在 code 目录下，用项目 conda 环境）：
    python scripts/rebuild_plan_copy_index.py
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# 保证能 import 到 app_v2
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select

from app_v2.core.embedding import embeddings
from app_v2.db.session import SessionLocal
from app_v2.models import ResponsePlan
from app_v2.services.knowledge_service import vector_store
from app_v2.services.plan_copy_index import (
    COLLECTION,
    build_plan_copy_record,
)


async def rebuild() -> None:
    """全量重建：遍历所有已 closed 方案，符合准入的重新写入。"""
    if not embeddings.configured:
        print("[skip] 未配置 SILICONFLOW_API_KEY，无法生成向量，跳过重建")
        return

    async with SessionLocal() as session:
        result = await session.execute(
            select(ResponsePlan.content_id).where(ResponsePlan.status == "closed")
        )
        content_ids = [r[0] for r in result.all()]

    if not content_ids:
        print("[skip] 没有已 closed 的方案记录")
        return

    written = 0
    skipped = 0
    for cid in content_ids:
        async with SessionLocal() as session:
            record = await build_plan_copy_record(session, cid)
        if record is None:
            skipped += 1
            print(f"[skip] 不符合准入（非 dm/public 或无文案）：{cid}")
            continue
        vec = await embeddings.embed_query(record["document"])
        if vec is None:
            skipped += 1
            print(f"[skip] 向量化失败：{cid}")
            continue
        try:
            vector_store.upsert(
                COLLECTION,
                ids=[record["id"]],
                documents=[record["document"]],
                metadatas=[record["metadata"]],
                embeddings=[vec],
            )
            written += 1
            print(f"[ok] {record['id']}")
        except Exception as exc:
            skipped += 1
            print(f"[skip] 写入失败：{cid}，原因：{exc}")

    print(f"\n重建完成：写入 {written} 条，跳过 {skipped} 条")


if __name__ == "__main__":
    asyncio.run(rebuild())
