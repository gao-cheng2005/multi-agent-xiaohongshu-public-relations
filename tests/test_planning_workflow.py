import pytest


class FakeChannel:
    action = "public"
    reason = "误解类内容，公开回应可挽回印象"


class FakeDraft:
    text = "您好，我们很重视您的反馈，请问是在哪个渠道购买的？"


class FakeScorePass:
    score = 9
    passed = True
    feedback = "很好"
    dimension_scores = {"tone": 9, "fact": 9, "actionable": 9}


class FakeScoreFail:
    score = 6
    passed = False
    feedback = "语气太生硬，请更温和"
    dimension_scores = {"tone": 6, "fact": 9, "actionable": 9}


def _seed():
    return {
        "content_id": "abc",
        "title": "体验差",
        "body": "产品不好用",
        "sentiment": "负面",
        "risk_level": "中",
        "risk_reason": "评论区出现体验差反馈",
        "urgent": False,
        "rounds": 0,
    }


async def test_planning_flow_generates(monkeypatch):
    from app_v2.services.workflows import planning_workflow as pw
    async def fake_channel(p):
        return FakeChannel()

    async def fake_draft(p):
        return FakeDraft()

    async def fake_score(p):
        return FakeScorePass()

    monkeypatch.setattr(pw, "run_channel_agent", fake_channel)
    monkeypatch.setattr(pw, "run_draft_agent", fake_draft)
    monkeypatch.setattr(pw, "run_score_agent", fake_score)

    stored = {}

    async def store(state):
        stored.update(state)

    graph = pw.build_planning_workflow(store_plan=store)
    out = await graph.ainvoke(_seed())
    assert out["channel"] == "public"
    assert out["status"] == "done"
    assert stored["draft_text"] == FakeDraft.text


async def test_planning_loop_rewrites_then_done(monkeypatch):
    from app_v2.services.workflows import planning_workflow as pw
    calls = {"score": 0, "draft": 0}
    async def fake_channel(p):
        return FakeChannel()

    monkeypatch.setattr(pw, "run_channel_agent", fake_channel)

    async def fake_draft(p):
        calls["draft"] += 1
        return type("D", (), {"text": f"第{calls['draft']}版文案"})

    async def fake_score(p):
        calls["score"] += 1
        return FakeScorePass() if calls["score"] >= 2 else FakeScoreFail()

    monkeypatch.setattr(pw, "run_draft_agent", fake_draft)
    monkeypatch.setattr(pw, "run_score_agent", fake_score)

    stored = {}

    async def store(state):
        stored.update(state)

    graph = pw.build_planning_workflow(store_plan=store)
    out = await graph.ainvoke(_seed())
    # 第一轮不达标 → 回 draft 重写 → 第二轮达标，共两轮
    assert out["rounds"] == 2
    assert out["score"] == 9
    assert out["status"] == "done"
    # 落库里应是最新一版文案
    assert stored["draft_text"] == "第2版文案"
