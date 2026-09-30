import pytest


async def test_analysis_graph_sentiment_and_risk(monkeypatch):
    from app_v2.services.workflows import analysis_workflow as wf

    # 替换分析服务层的两个函数，验证图接线（不真实调大模型）
    async def fake_sentiment(note):
        return {"sentiment": "负面", "confidence": 0.9, "model": "fake"}

    async def fake_risk(note, comments=None):
        return {
            "risk_level": "高", "summary": "实锤指控", "score": 9,
            "harm_score": 9, "spread_score": 6, "urgent": True, "model": "fake",
        }

    monkeypatch.setattr(wf, "analyze_sentiment", fake_sentiment)
    monkeypatch.setattr(wf, "analyze_risk", fake_risk)

    graph = wf.build_analysis_workflow()
    state = {
        "content_id": "abc",
        "title": "假货避雷",
        "body": "这个牌子是假货，大家别买",
        "like_count": 100,
        "collect_count": 50,
        "share_count": 10,
        "comment_count": 20,
        "published_at": "2026-09-19",
        "comments": [],
    }
    result = await graph.ainvoke(state)
    assert result["sentiment"] == "负面"
    assert result["analysis"]["risk_level"] == "高"
    assert result["analysis"]["harm_score"] == 9


async def test_rule_risk_fallback():
    # 无密钥时走规则兜底
    from app_v2.services.agents.sentiment_agent import rule_risk

    result = rule_risk("这个全是假货，垃圾", ["别买，避雷"])
    assert result["risk_level"] == "高"
    assert result["urgent"] is True


async def test_analyze_risk_without_key_uses_rule(monkeypatch):
    from app_v2.core.settings import settings
    monkeypatch.setattr(settings, "siliconflow_api_key", "")
    from app_v2.services.agents.sentiment_agent import analyze_risk

    result = await analyze_risk({"title": "假货", "body": "全是假货别买"}, [])
    assert result["model"] == "rule"


async def test_issues_node_marks_unknown_dimensions_unconfirmed(monkeypatch):
    """Agent⑥ 输出预定义维度→正式；新发现维度→待确认（confirmed=False）。"""
    from app_v2.services.workflows import post_collect_workflow as wf
    from app_v2.services.agents import prompts

    class FakeResult:
        items = [
            type("I", (), {"dimension": "做工/材质", "dimension_def": "", "label": "塑料感", "polarity": "negative", "source": "note", "author": "作者", "excerpt": "塑料感强"})(),
            type("I", (), {"dimension": "自动关灯", "dimension_def": "台灯自己亮起/误触发", "label": "半夜自己亮", "polarity": "negative", "source": "comment", "author": "用户A", "excerpt": "半夜自己亮"})(),
        ]

    async def fake_tagger(payload):
        return FakeResult()

    monkeypatch.setattr(wf, "run_issue_tagger", fake_tagger)
    state = {"product": "米家台灯2 Lite", "content": {"title": "t", "body": "b"}, "comments": []}
    out = await wf._issues_node(state)
    items = {i["dimension"]: i for i in out["issue_items"]}
    assert items["做工/材质"]["confirmed"] is True
    assert items["自动关灯"]["confirmed"] is False

    # DIMENSION_NAMES 与大纲首词一致（防以后改大纲不同步）
    assert "做工/材质" in prompts.DIMENSION_NAMES
