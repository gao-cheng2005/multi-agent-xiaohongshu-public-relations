# -*- coding: utf-8 -*-
"""
查看 ChromaDB 向量数据库里的数据（只读，不影响库）。

用法示例（在项目目录下，用项目的 conda 环境运行）：
    C:/Users/HUAWEI/.conda/envs/agent_project_1/python.exe scripts/view_chroma.py
    C:/Users/HUAWEI/.conda/envs/agent_project_1/python.exe scripts/view_chroma.py --path data/chroma
    C:/Users/HUAWEI/.conda/envs/agent_project_1/python.exe scripts/view_chroma.py --collection plan_copy_library --limit 20
    C:/Users/HUAWEI/.conda/envs/agent_project_1/python.exe scripts/view_chroma.py --vectors --limit 2   # 附带向量预览
    C:/Users/HUAWEI/.conda/envs/agent_project_1/python.exe scripts/view_chroma.py --json > dump.json   # 输出为 JSON
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Windows 命令行输出统一用 UTF-8，避免中文显示成乱码
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# 项目里 ChromaDB 默认持久化目录（code/data/chroma），可通过 --path 覆盖
DEFAULT_PERSIST_DIR = Path(__file__).resolve().parent.parent / "data" / "chroma"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="查看 ChromaDB 向量数据库中的数据（只读）",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--path", default=str(DEFAULT_PERSIST_DIR),
                        help="ChromaDB 持久化目录（含 chroma.sqlite3）")
    parser.add_argument("--collection", default=None,
                        help="只看指定集合；不填则列出全部集合")
    parser.add_argument("--limit", type=int, default=5,
                        help="每个集合最多输出多少条记录")
    parser.add_argument("--skip", type=int, default=0,
                        help="跳过前 N 条记录（分页）")
    parser.add_argument("--vectors", action="store_true",
                        help="附带输出向量（只预览前 8 个维度和总维度）")
    parser.add_argument("--json", action="store_true",
                        help="以 JSON 格式输出（适合管道/存文件）")
    parser.add_argument("--where", default=None,
                        help="过滤条件，例如 channel=dm 或 sentiment=负面（多个用 & 连接）")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    persist_dir = Path(args.path)
    if not (persist_dir / "chroma.sqlite3").exists():
        print(f"[错误] 没有找到 ChromaDB 数据库：{persist_dir}/chroma.sqlite3", file=sys.stderr)
        raise SystemExit(1)

    try:
        import chromadb
        from chromadb.config import Settings as ChromaSettings
    except ImportError as exc:
        print("[错误] 当前环境缺少 chromadb，请用项目的 conda 环境运行：", file=sys.stderr)
        print("  C:/Users/HUAWEI/.conda/envs/agent_project_1/python.exe " + __file__, file=sys.stderr)
        raise SystemExit(1) from exc

    client = chromadb.PersistentClient(
        path=str(persist_dir), settings=ChromaSettings(anonymized_telemetry=False)
    )

    # 构造 where 过滤
    where = None
    if args.where:
        pairs = {}
        for part in args.where.split("&"):
            if "=" in part:
                k, v = part.split("=", 1)
                pairs[k.strip()] = v.strip()
        if len(pairs) == 1:
            where = {k: v for k, v in pairs.items()}
        elif len(pairs) > 1:
            where = {"$and": [{k: v} for k, v in pairs.items()]}

    include = ["documents", "metadatas"]
    if args.vectors:
        include.append("embeddings")

    collections = [c for c in client.list_collections()
                   if args.collection is None or c.name == args.collection]
    if not collections:
        print(f"[提示] 没有找到集合{'（' + args.collection + '）' if args.collection else ''}")
        return

    result = {"persist_dir": str(persist_dir), "collections": []}

    for col in collections:
        total = col.count()
        get_args = dict(limit=args.limit, offset=args.skip, include=include)
        if where:
            get_args["where"] = where
        try:
            got = col.get(**get_args)
        except Exception as exc:  # 例如 where 字段名不存在
            print(f"[警告] 集合 [{col.name}] 查询失败：{exc}", file=sys.stderr)
            continue

        ids = got.get("ids") or []
        docs = (got.get("documents") or [None] * len(ids))
        metas = got.get("metadatas") or [None] * len(ids)
        vecs = got.get("embeddings")  # 可能为 None

        if args.json:
            rows = []
            for i, cid in enumerate(ids):
                row = {"id": cid}
                if docs and docs[i] is not None:
                    row["document"] = docs[i]
                if metas and metas[i] is not None:
                    row["metadata"] = metas[i]
                if vecs is not None and vecs[i] is not None:
                    row["vector"] = _vector_preview(vecs[i])
                rows.append(row)
            result["collections"].append({
                "name": col.name,
                "count": total,
                "shown": len(rows),
                "offset": args.skip,
                "records": rows,
            })
            continue

        print(f"\n{'=' * 70}")
        print(f"集合: {col.name}    总数: {total}    本次显示: {len(ids)} (页码 offset={args.skip})")
        print(f"{'=' * 70}")
        for i, cid in enumerate(ids):
            print(f"\n[{i + args.skip + 1}] id = {cid}")
            if docs and docs[i] is not None:
                print(f"    document : {docs[i]}")
            if metas and metas[i] is not None:
                print(f"    metadata : {json.dumps(metas[i], ensure_ascii=False)}")
            if vecs is not None and vecs[i] is not None:
                print(f"    vector   : {_vector_preview(vecs[i])}")

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))


def _vector_pretext(v) -> str:
    return (json.dumps(v, ensure_ascii=False) if len(v) <= 16 else
            json.dumps(v[:16], ensure_ascii=False) + ", ...（共" + str(len(v)) + "维）")


def _vector_preview(v) -> str:
    if v is None:
        return "无"
    n = len(v)
    head = ", ".join(f"{x:.3f}" if isinstance(x, float) else str(x) for x in v[:8])
    return f"[{head}, ...] 共 {n} 维"


if __name__ == "__main__":
    main()