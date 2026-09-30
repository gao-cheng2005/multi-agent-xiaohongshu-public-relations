# -*- coding: utf-8 -*-
"""
scripts/clear_plan_copy_index 清除文案话术库（RAG 向量库）数据。

安全边界（重要）：
- 只清理 ChromaDB 里的 RAG 索引（plan_copy_library 集合 / data/chroma 目录）；
- MySQL 业务库（笔记、评论、分析、方案等）完全不受影响；
- 清除后数据可随时用 scripts/rebuild_plan_copy_index.py 全量重建。

用法（code 目录下，用项目 conda 环境）：
    python scripts/clear_plan_copy_index.py          # 只删 plan_copy_library 集合
    python scripts/clear_plan_copy_index.py --all    # 连 data/chroma 目录一起删除
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

# 保证能 import 到 app_v2
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app_v2.services.plan_copy_index import COLLECTION


def clear_collection() -> None:
    """只删除文案话术库集合（保留 data/chroma 目录与其它集合）。"""
    from app_v2.services.knowledge_service import vector_store

    client = vector_store.client
    names = {c.name for c in client.list_collections()}
    if COLLECTION in names:
        client.delete_collection(COLLECTION)
        print(f"[ok] 已删除集合：{COLLECTION}")
    else:
        print(f"[skip] 集合 {COLLECTION} 不存在（没有可清的）")

    remaining = [c.name for c in client.list_collections()]
    print(f"剩余集合：{remaining if remaining else '（无）'}")


def clear_all() -> None:
    """整体删除 data/chroma 目录（推到重建脚本重新灌入）。"""
    persist = Path("data/chroma")
    if persist.is_dir():
        shutil.rmtree(persist, ignore_errors=True)
        print(f"[ok] 已整体删除目录：{persist.resolve()}")
    else:
        print(f"[skip] 目录不存在：{persist.resolve()}")
    print("如需重新灌入历史已 closed 方案的文案，运行：python scripts/rebuild_plan_copy_index.py")


def main() -> None:
    parser = argparse.ArgumentParser(description="清除文案话术库（RAG 向量库）")
    parser.add_argument(
        "--all",
        action="store_true",
        help="整体删除 data/chroma 目录（默认只删 plan_copy_library 集合）",
    )
    args = parser.parse_args()

    if args.all:
        clear_all()
    else:
        clear_collection()


if __name__ == "__main__":
    main()