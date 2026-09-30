"""Agent④ 文案节点 RAG 集成测试：命中时注入参考、失败/无结果时静默降级。"""
import pytest


class FakeDraft:
    text = "您好，我们很重视您的反馈"


def _state(**overrides):
    base = {
        "content_id": "abc",
        "title": "台灯发热",
        "body": "用了几天发热严重",
        "sentiment": "负面",
        "risk_level": "中",
        "risk_reason": "发热反馈",
        "channel": "public",
        "dimensions": ["发热/散热"],
        "feedback": "",
        "human_feedback": "",
    }
    base.update(overrides)
    return base


async def test_draft_node_injects_references(monkeypatch):
    from app_v2.services.workflows import planning_workflow as pw

    captured = {}

    async def fake_search(query):
        captured["query"] = query
        return [{"metadata": {"copy_text": "已关注，我们会核实处理", "title": "发热问题"}}]

    async def fake_draft(payload):
        captured["payload"] = payload
        return FakeDraft()

    monkeypatch.setattr(
        "app_v2.services.plan_copy_index.search_references", fake_search
    )
    monkeypatch.setattr(pw, "run_draft_agent", fake_draft)

    out = await pw._draft_node(_state())
    assert out["draft_text"] == FakeDraft.text
    # 查询应带 sentiment/risk/channel + 标题正文 + 维度
    assert captured["query"]["sentiment"] == "负面"
    assert captured["query"]["channel"] == "public"
    assert captured["query"]["dimensions"] == ["发热/散热"]
    # 生成 payload 应包含历史参考文案
    assert "历史完成处理时采用的文案参考" in captured["payload"]
    assert "已关注，我们会核实处理" in captured["payload"]


async def test_draft_node_silent_when_no_references(monkeypatch):
    from app_v2.services.workflows import planning_workflow as pw

    captured = {}

    async def fake_search(query):
        return []

    async def fake_draft(payload):
        captured["payload"] = payload
        return FakeDraft()

    monkeypatch.setattr(
        "app_v2.services.plan_copy_index.search_references", fake_search
    )
    monkeypatch.setattr(pw, "run_draft_agent", fake_draft)

    await pw._draft_node(_state())
    # 无参考时 payload 不应出现参考文案段
    assert "历史完成处理时采用的文案参考" not in captured["payload"]


async def test_draft_node_silent_when_search_raises(monkeypatch):
    from app_v2.services.workflows import planning_workflow as pw

    captured = {}

    async def fake_search(query):
        raise RuntimeError("embedding api down")

    async def fake_draft(payload):
        captured["payload"] = payload
        return FakeDraft()

    monkeypatch.setattr(
        "app_v2.services.plan_copy_index.search_references", fake_search
    )
    monkeypatch.setattr(pw, "run_draft_agent", fake_draft)

    out = await pw._draft_node(_state())
    assert out["draft_text"] == FakeDraft.text
    assert "历史完成处理时采用的文案参考" not in captured["payload"]
