"""RAG 基础设施（M0）单元测试：BM25 / 混合检索 / 文案库工具函数。"""
import pytest


# ---------------------------------------------------------------------------
# BM25
# ---------------------------------------------------------------------------

def test_bm25_tokenize():
    from app_v2.core.bm25 import tokenize

    words = tokenize("米家台灯发热严重，散热差")
    assert "发热" in words or "散热" in words
    assert tokenize("") == []


def test_bm25_search_ranks_keywords():
    from app_v2.core.bm25 import BM25Index

    index = BM25Index(["台灯发热严重", "续航不行", "发热并且频闪"])
    ranked = index.search("发热", top_k=2)
    # 返回的是 (文档下标, 分数)，第一个下标应是含"发热"的文档（0 或 2）
    assert ranked
    assert ranked[0][0] in (0, 2)


def test_bm25_empty_corpus_safe():
    from app_v2.core.bm25 import BM25Index

    assert BM25Index([]).search("发热") == []
    assert BM25Index(["a", "b"]).search("") == []


# ---------------------------------------------------------------------------
# 混合检索 RRF
# ---------------------------------------------------------------------------

def test_rrf_fuse_merges_rankings():
    from app_v2.services.retrieval import _rrf_fuse

    fused = _rrf_fuse({"a": 1, "b": 2}, {"a": 2, "c": 1})
    # a 在两路都出现，分数应更高
    assert fused["a"] > fused["b"]
    assert fused["a"] > fused["c"]


def test_top_candidates_orders_and_caps():
    from app_v2.services.retrieval import _top_candidates

    candidates = [{"id": "a"}, {"id": "b"}, {"id": "c"}]
    fused = {"c": 0.9, "a": 0.5, "b": 0.1}
    out = _top_candidates(candidates, fused, top_k=2)
    assert [x["id"] for x in out] == ["c", "a"]


# ---------------------------------------------------------------------------
# 文案话术库工具函数
# ---------------------------------------------------------------------------

def test_build_document_truncates_and_joins():
    from app_v2.services.plan_copy_index import build_document

    doc = build_document("标题" * 300, "正文" * 300, ["发热/散热", "频闪"])
    assert "问题标签：" in doc
    assert "发热/散热" in doc
    # 标题/正文各截断 200 字
    assert len(doc.split("\n")[0]) == 200
    assert len(doc.split("\n")[1]) == 200


def test_build_document_empty_fallback():
    from app_v2.services.plan_copy_index import build_document

    assert build_document("", "", []) == "（无标题）"


def test_build_where_single_condition():
    from app_v2.services.plan_copy_index import _build_where

    assert _build_where({"sentiment": "负面"}) == {"sentiment": "负面"}
    assert _build_where({}) is None


def test_build_where_and_with_dimension():
    from app_v2.services.plan_copy_index import _build_where

    where = _build_where({
        "sentiment": "负面",
        "risk_level": "中",
        "channel": "public",
        "dimensions": ["发热/散热"],
    })
    assert where == {
        "$and": [
            {"sentiment": "负面"},
            {"risk_level": "中"},
            {"channel": "public"},
            {"dimensions": {"$contains": "发热/散热"}},
        ]
    }


def test_format_references_with_copy():
    from app_v2.services.plan_copy_index import format_references

    refs = [{"metadata": {"copy_text": "感谢反馈，我们会核实处理", "title": "台灯发热"}}]
    text = format_references(refs, "public")
    assert "历史完成处理时采用的文案参考" in text
    assert "感谢反馈，我们会核实处理" in text
    assert "渠道=公开评论" in text


def test_format_references_empty():
    from app_v2.services.plan_copy_index import format_references

    assert format_references([], "dm") == ""
    # 无 copy_text 的无效参考也不输出
    assert format_references([{"metadata": {"copy_text": "", "title": "x"}}], "dm") == ""
