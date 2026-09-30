# -*- coding: utf-8 -*-
"""
scripts/inspect_plan_copy_index 文案话术库检查脚本（只读，不写数据）。

用途：验证「完成处理时采用的文案」是否已成功存入向量库（ChromaDB）。
与 MySQL 无关——向量库独立持久化在 data/chroma，本脚本只读 ChromaDB。

用法（code 目录下，用项目 conda 环境；Windows 控制台乱码时先执行 chcp 65001）：
    python scripts/inspect_plan_copy_index.py                        # 统计 + 列出全部
    python scripts/inspect_plan_copy_index.py --limit 10             # 只看前 10 条
    python scripts/inspect_plan_copy_index.py --content-id 64xxxxx   # 查某篇笔记是否入库
    python scripts/inspect_plan_copy_index.py --channel public       # 按处理渠道过滤
    python scripts/inspect_plan_copy_index.py --query "台灯发热严重"  # 模拟检索（无需开 RAG_ENABLED）
    python scripts/inspect_plan_copy_index.py --query "台灯发热" --channel public --sentiment 负面 --risk 中
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

# 保证能 import 到 app_v2
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app_v2.services.knowledge_service import vector_store
from app_v2.services.plan_copy_index import COLLECTION, format_references

CHANNEL_LABEL = {"dm": "私信", "public": "公开评论", "skip": "无需处理"}


def _collection() -> tuple[bool, object]:
    """拿到集合；不存在返回 (False, None)。"""
    client = vector_store.client
    names = {c.name for c in client.list_collections()}
    if COLLECTION not in names:
        return False, None
    return True, client.get_collection(COLLECTION)


def dump_records(col, where: dict | None, limit: int) -> None:
    """列出（过滤后的）全部记录：渠道/情感/风险/维度 + 文案前 60 字。"""
    result = col.get(where=where, include=["documents", "metadatas"])
    ids = result.get("ids") or []
    metadatas = result.get("metadatas") or []

    print(f"\n共 {len(ids)} 条" + (f"（where={where}）" if where else "") + "，展示前 %d 条：" % limit)
    if not ids:
        print("  （无记录 → 还没有发生符合条件的入库）")
        return

    for i, _id in enumerate(ids[:limit]):
        md = metadatas[i] or {}
        ch = md.get("channel", "?")
        copy = (md.get("copy_text") or "").replace("\n", " ")
        print(f"  [{i + 1}] id={_id}")
        print(f"       渠道={CHANNEL_LABEL.get(ch, ch)} 情感={md.get('sentiment','?')} "
              f"风险={md.get('risk_level','?')} 维度={md.get('dimensions') or '无'}")
        print(f"       标题={md.get('title','')}")
        print(f"       文案={copy[:60]}")


def verify_content(col, content_id: str) -> int:
    """按笔记 ID 精确验证：返回命中的记录数。"""
    result = col.get(where={"content_id": content_id}, include=["metadatas"])
    ids = result.get("ids") or []
    metadatas = result.get("metadatas") or []
    print(f"\n笔记 {content_id} 入库记录数：{len(ids)}")
    for _id, md in zip(ids, metadatas):
        ch = md.get("channel", "?")
        copy = (md.get("copy_text") or "").replace("\n", " ")
        print(f"  ✅ id={_id} 渠道={CHANNEL_LABEL.get(ch, ch)} 情感={md.get('sentiment','?')} "
              f"风险={md.get('risk_level','?')} 文案={copy[:60]}")
    if not ids:
        print("  ❌ 未入库。可能原因：")
        print("     1. 该笔记还没点过「完成处理」；")
        print("     2. 方案不是 dm/public（如 skip 无需处理，不入库）；")
        print("     3. 对应渠道文案为空；")
        print("     4. 后台写入失败（看后端日志 rag.plan_copy_index WARNING）。")
    return len(ids)


async def query_demo(args) -> None:
    """模拟一次 Agent④ 检索：直接用混合检索，不依赖 RAG_ENABLED 开关。"""
    from app_v2.services.plan_copy_index import _build_where, build_document
    from app_v2.services.retrieval import hybrid_search

    # 复用真实检索逻辑（向量 + BM25 + RRF，失败静默降级）
    query_text = build_document(args.query, "", [])
    where = _build_where({
        "sentiment": args.sentiment,
        "risk_level": args.risk,
        "channel": args.channel,
        "dimensions": [],
    })
    refs = await hybrid_search(COLLECTION, query_text, where, top_k=5)

    print(f"\n检索「{args.query}」命中 {len(refs)} 条参考：")
    if not refs:
        print("  （无命中 → 库里没有相似文案）")
        return
    # 把前源信息打出来，方便对照
    for i, ref in enumerate(refs, start=1):
        md = ref.get("metadata") or {}
        print(f"  [{i}] score={ref.get('score', '?')} 渠道={md.get('channel','?')} "
              f"标题={md.get('title','')} 文案={md.get('copy_text','')[:60]}")
    print("\n--- 拼进 Agent④ 的 few-shot 效果预览 ---")
    print(format_references(refs, args.channel or "public"))


def main() -> None:
    parser = argparse.ArgumentParser(description="文案话术库检查（只读 ChromaDB）")
    parser.add_argument("--limit", type=int, default=50, help="最多展示条数")
    parser.add_argument("--content-id", default="", help="按笔记 ID 验证是否入库")
    parser.add_argument("--channel", default="", choices=["dm", "public"], help="按渠道过滤")
    parser.add_argument("--query", default="", help="模拟检索的文本（不用开 RAG_ENABLED）")
    parser.add_argument("--sentiment", default="", help="检索过滤：情感（正面/中性/负面）")
    parser.add_argument("--risk", default="", help="检索过滤：风险（低/中/高）")
    args = parser.parse_args()

    exists, col = _collection()
    print(f"向量库集合：{COLLECTION}  |  存在：{'是' if exists else '否'}")
    if not exists:
        print("\n还没有 plan_copy_library 集合 → 尚未发生过任何入库。")
        print("验证步骤：对一篇有方案（dm/public）的笔记点「完成处理」，")
        print("          等 1~2 秒异步写入后，再用 --content-id 检查。")
        return

    if args.query:
        asyncio.run(query_demo(args))
        return

    if args.content_id:
        verify_content(col, args.content_id)
        return

    where = {"channel": args.channel} if args.channel else None
    dump_records(col, where, args.limit)


if __name__ == "__main__":
    main()