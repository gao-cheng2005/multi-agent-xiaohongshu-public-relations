"""混合检索（向量 + 关键词，RRF 融合）。

用于文案话术库等 RAG 场景：先用结构化过滤收窄范围，再在候选集合里同时做
向量语义检索和关键词字面检索，用 RRF 把两路排序融合成一路。

原则：向量接口不可用时降级为纯关键词检索；全程失败静默返回空。
"""

from __future__ import annotations

from ..core.bm25 import BM25Index
from ..core.embedding import embeddings
from .knowledge_service import vector_store

# RRF 融合常数：score = Σ 1 / (k + rank)
RRF_K = 60


async def hybrid_search(
    collection_name: str,
    query_text: str,
    where: dict | None,
    top_k: int = 3,
) -> list[dict]:
    """混合检索：向量 + 关键词 → RRF 融合 → top-k，返回候选列表。"""
    try:
        # 先按过滤条件取出全部候选，作为关键词检索的文档池
        candidates = vector_store.get_all(collection_name, where)
        if not candidates:
            return []

        # 两路分别打分，再融合
        vector_rank = await _vector_rank(collection_name, query_text, where, top_k)
        bm25_rank = _bm25_rank(candidates, query_text, top_k)

        fused = _rrf_fuse(vector_rank, bm25_rank)
        return _top_candidates(candidates, fused, top_k)
    except Exception:
        return []


async def _vector_rank(
    collection_name: str,
    query_text: str,
    where: dict | None,
    top_k: int,
) -> dict[str, int]:
    """向量检索，返回 {id: 排名}（排名从 1 开始）；失败返回空。"""
    vec = await embeddings.embed_query(query_text)
    if vec is None:
        return {}
    try:
        items = vector_store.query(collection_name, vec, where, top_k)
    except Exception:
        return {}
    return {item["id"]: rank for rank, item in enumerate(items, start=1)}


def _bm25_rank(candidates: list[dict], query_text: str, top_k: int) -> dict[str, int]:
    """关键词检索，返回 {id: 排名}。"""
    docs = [c.get("document") or "" for c in candidates]
    index = BM25Index(docs)
    ranked = index.search(query_text, top_k)
    return {
        candidates[idx]["id"]: rank
        for rank, (idx, _score) in enumerate(ranked, start=1)
    }


def _rrf_fuse(*rankings: dict[str, int]) -> dict[str, float]:
    """把多路排名融合成一个分数，返回 {id: rrf_score}。"""
    scores: dict[str, float] = {}
    for ranking in rankings:
        for _id, rank in ranking.items():
            scores[_id] = scores.get(_id, 0.0) + 1.0 / (RRF_K + rank)
    return scores


def _top_candidates(candidates: list[dict], fused: dict[str, float], top_k: int) -> list[dict]:
    """按融合分数排序，返回 top-k 候选，并把分数附到结果里。"""
    by_id = {c["id"]: c for c in candidates}
    ordered = sorted(fused.items(), key=lambda kv: kv[1], reverse=True)
    result: list[dict] = []
    for _id, score in ordered[:top_k]:
        if _id in by_id:
            result.append({**by_id[_id], "score": score})
    return result
