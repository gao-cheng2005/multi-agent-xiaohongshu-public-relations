"""文案话术库索引服务单元测试：检索开关 / 空内容降级 / 查询构造。"""
import asyncio

import pytest


def test_search_references_disabled_returns_empty(monkeypatch):
    from app_v2.core.settings import settings
    from app_v2.services.plan_copy_index import search_references

    monkeypatch.setattr(settings, "rag_enabled", False)
    result = asyncio.run(
        search_references({"title": "台灯发热", "body": "发热严重"})
    )
    assert result == []


def test_search_references_empty_content_returns_empty(monkeypatch):
    from app_v2.core.settings import settings
    from app_v2.services.plan_copy_index import search_references

    monkeypatch.setattr(settings, "rag_enabled", True)
    # 标题/正文/维度全空 → 不应触发检索
    result = asyncio.run(search_references({}))
    assert result == []


def test_search_references_calls_hybrid(monkeypatch):
    from app_v2.core.settings import settings
    from app_v2.services.plan_copy_index import search_references

    monkeypatch.setattr(settings, "rag_enabled", True)
    monkeypatch.setattr(settings, "rag_top_k", 5)

    captured = {}

    async def fake_hybrid(collection, query_text, where, top_k):
        captured["collection"] = collection
        captured["query_text"] = query_text
        captured["where"] = where
        captured["top_k"] = top_k
        return [{"id": "x", "metadata": {"copy_text": "文案", "title": "标题"}}]

    monkeypatch.setattr(
        "app_v2.services.plan_copy_index.hybrid_search", fake_hybrid
    )

    result = asyncio.run(
        search_references({
            "title": "台灯发热",
            "body": "发热严重",
            "sentiment": "负面",
            "risk_level": "中",
            "channel": "public",
            "dimensions": ["发热/散热"],
        })
    )
    assert len(result) == 1
    assert captured["collection"] == "plan_copy_library"
    assert captured["top_k"] == 5
    assert "台灯发热" in captured["query_text"]
    assert captured["where"] == {
        "$and": [
            {"sentiment": "负面"},
            {"risk_level": "中"},
            {"channel": "public"},
            {"dimensions": {"$contains": "发热/散热"}},
        ]
    }


def test_search_references_swallows_hybrid_error(monkeypatch):
    from app_v2.core.settings import settings
    from app_v2.services.plan_copy_index import search_references

    monkeypatch.setattr(settings, "rag_enabled", True)

    async def fake_hybrid(collection, query_text, where, top_k):
        raise RuntimeError("chroma down")

    monkeypatch.setattr(
        "app_v2.services.plan_copy_index.hybrid_search", fake_hybrid
    )

    result = asyncio.run(
        search_references({"title": "台灯发热", "body": "发热严重"})
    )
    assert result == []
