"""混合检索集成测试：真实 ChromaDB（临时目录）+ 假 embedding，验证写入/检索/降级。"""
import asyncio
import tempfile

import pytest


@pytest.fixture()
def fresh_vector_store(monkeypatch):
    from app_v2.core.settings import settings
    from app_v2.services.knowledge_service import vector_store

    # 用临时目录隔离 ChromaDB，避免污染正式数据
    monkeypatch.setattr(settings, "chroma_persist_dir", tempfile.mkdtemp())
    vector_store._client = None
    return vector_store


def test_hybrid_search_returns_matching(monkeypatch, fresh_vector_store):
    from app_v2.core.embedding import embeddings as embedding_svc
    from app_v2.services.retrieval import hybrid_search
    from app_v2.services.plan_copy_index import COLLECTION

    # 预置两条记录（显式向量，避免触发本地 ONNX）
    fresh_vector_store.upsert(
        COLLECTION,
        ids=["n1:public", "n2:public"],
        documents=["台灯发热严重，散热差", "续航短电池不耐用"],
        metadatas=[
            {
                "sentiment": "负面",
                "risk_level": "中",
                "channel": "public",
                "dimensions": ["发热/散热"],
                "copy_text": "已关注发热问题",
                "content_id": "n1",
                "title": "台灯发热",
            },
            {
                "sentiment": "负面",
                "risk_level": "中",
                "channel": "public",
                "dimensions": ["续航/电源"],
                "copy_text": "已关注续航问题",
                "content_id": "n2",
                "title": "续航短",
            },
        ],
        embeddings=[[0.1] * 8, [0.9] * 8],
    )

    async def fake_embed_query(text):
        # 让查询向量贴近 n1（发热）
        return [0.1] * 8

    monkeypatch.setattr(embedding_svc, "embed_query", fake_embed_query)

    where = {
        "$and": [
            {"sentiment": "负面"},
            {"risk_level": "中"},
            {"channel": "public"},
            {"dimensions": {"$contains": "发热/散热"}},
        ]
    }

    result = asyncio.run(hybrid_search(COLLECTION, "台灯发热", where, top_k=3))
    assert result
    # 结构化过滤 + 向量贴近 n1 → 应命中发热那条
    assert result[0]["metadata"]["content_id"] == "n1"
    assert result[0]["metadata"]["copy_text"] == "已关注发热问题"


def test_hybrid_search_empty_collection(monkeypatch, fresh_vector_store):
    from app_v2.core.embedding import embeddings as embedding_svc
    from app_v2.services.retrieval import hybrid_search

    async def fake_embed_query(text):
        return [0.5] * 8

    monkeypatch.setattr(embedding_svc, "embed_query", fake_embed_query)

    result = asyncio.run(hybrid_search("empty_collection_xyz", "查询", None, 3))
    assert result == []


def test_hybrid_search_embedding_fail_falls_back_to_bm25(monkeypatch, fresh_vector_store):
    from app_v2.core.embedding import embeddings as embedding_svc
    from app_v2.services.retrieval import hybrid_search
    from app_v2.services.plan_copy_index import COLLECTION

    fresh_vector_store.upsert(
        COLLECTION,
        ids=["n9:public"],
        documents=["台灯发热严重"],
        metadatas=[
            {
                "sentiment": "负面",
                "risk_level": "中",
                "channel": "public",
                "copy_text": "已关注",
                "content_id": "n9",
                "title": "台灯发热",
            }
        ],
        embeddings=[[0.3] * 8],
    )

    async def fake_embed_query(text):
        return None  # 模拟 embedding API 不可用

    monkeypatch.setattr(embedding_svc, "embed_query", fake_embed_query)

    result = asyncio.run(hybrid_search(COLLECTION, "台灯发热", {"channel": "public"}, 3))
    # embedding 失败 → 降级为 BM25，仍能按关键词召回
    assert result
    assert result[0]["metadata"]["content_id"] == "n9"
