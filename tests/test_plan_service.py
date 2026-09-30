import pytest


async def test_reset_stale_processing_empty(monkeypatch):
    from app_v2.services import plan_service as ps

    class FakeRepo:
        async def list(self, session):
            return []

    service = ps.PlanService.__new__(ps.PlanService)
    service.plan_repo = FakeRepo()
    service.session = None
    result = await service.reset_stale_processing()
    assert result == 0


async def test_reset_stale_processing_marks_failed(monkeypatch):
    from datetime import datetime, timezone, timedelta
    from app_v2.services import plan_service as ps

    class FakePlan:
        def __init__(self, pid, status, updated_at):
            self.id = pid
            self.status = status
            self.updated_at = updated_at

    stale = FakePlan("a", "processing", datetime.now(timezone.utc) - timedelta(minutes=15))
    fresh = FakePlan("b", "processing", datetime.now(timezone.utc) - timedelta(minutes=1))

    marked = []

    class FakeRepo:
        async def list(self, session):
            return [stale, fresh]

        async def mark_status(self, session, plan_id, status):
            marked.append((plan_id, status))

    service = ps.PlanService.__new__(ps.PlanService)
    service.plan_repo = FakeRepo()
    service.session = None
    count = await service.reset_stale_processing()
    assert count == 1
    assert ("a", "failed") in marked
    assert ("b", "failed") not in marked


async def test_create_returns_existing_done_without_regenerating(monkeypatch):
    from app_v2.services import plan_service as ps
    # to_dict 需要真实 ORM 对象，这里直接打桩成返回固定字典
    monkeypatch.setattr(ps, "to_dict", lambda row: {
        "status": row.status,
        "channel": row.channel,
        "comment_copy": row.comment_copy,
    })

    called = []

    class FakePlan:
        status = "done"
        channel = "public"
        comment_copy = "已生成文案"

    class FakeRepo:
        async def get_by_content_id(self, session, content_id):
            return FakePlan()

    service = ps.PlanService.__new__(ps.PlanService)
    service.session = object()
    service.plan_repo = FakeRepo()
    monkeypatch.setattr(service, "schedule_generation", lambda cid: called.append(cid))

    result = await service.create("n1")
    assert called == []                       # 已 done：不触发重新生成
    assert result["status"] == "done"
    assert result["comment_copy"] == "已生成文案"


async def test_create_regenerates_when_no_plan(monkeypatch):
    from app_v2.services import plan_service as ps
    monkeypatch.setattr(ps, "to_dict", lambda row: {"status": row.status})

    called = []

    class FakeRepo:
        async def get_by_content_id(self, session, content_id):
            return None                      # 没有方案

    service = ps.PlanService.__new__(ps.PlanService)
    service.session = object()
    service.plan_repo = FakeRepo()

    async def fake_gen(cid, force=False):
        called.append(cid)
        # 生成后仓库能查到 finished 方案
        async def _after(s, c):
            return type("P", (), {"status": "done"})()
        service.plan_repo.get_by_content_id = _after

    monkeypatch.setattr(service, "schedule_generation", fake_gen)

    result = await service.create("n1")
    assert called == ["n1"]                   # 无方案：正常生成一次
    assert result["status"] == "done"


async def test_create_returns_processing_without_regenerating(monkeypatch):
    from app_v2.services import plan_service as ps
    monkeypatch.setattr(ps, "to_dict", lambda row: {"status": row.status})

    called = []

    class FakePlan:
        status = "processing"

    class FakeRepo:
        async def get_by_content_id(self, session, content_id):
            return FakePlan()

    service = ps.PlanService.__new__(ps.PlanService)
    service.session = object()
    service.plan_repo = FakeRepo()
    monkeypatch.setattr(service, "schedule_generation", lambda cid: called.append(cid))

    result = await service.create("n1")
    assert called == []                       # 生成中：不重复起任务
    assert result["status"] == "processing"


async def test_complete_skipped_plan_marks_closed_with_skip(monkeypatch):
    """正面/中性 + 低风险的 skipped 方案点"完成处理"后应变为 closed 且渠道为 skip。"""
    from app_v2.services import plan_service as ps

    monkeypatch.setattr(ps, "to_dict", lambda row: {"status": row.status, "channel": row.channel})
    instances = []

    class FakePlan:
        def __init__(self):
            self.status = "skipped"
            self.channel = "skip"
            self.decided_at = None
            self.decided_by = ""
            instances.append(self)

    class FakeRepo:
        async def get_by_content_id(self, session, content_id):
            return FakePlan()

    class FakeSession:
        async def flush(self):
            return None

    service = ps.PlanService.__new__(ps.PlanService)
    service.session = FakeSession()
    service.plan_repo = FakeRepo()

    result = await service.complete("n1", "op")
    assert result["status"] == "closed"
    assert result["channel"] == "skip"
    assert instances[0].decided_at is not None
    assert instances[0].decided_by == "op"


async def test_complete_done_plan_preserves_channel(monkeypatch):
    """已生成方案（done）完成处理时，渠道（dm/public）必须保持不变。"""
    from app_v2.services import plan_service as ps

    monkeypatch.setattr(ps, "to_dict", lambda row: {"status": row.status, "channel": row.channel})

    class FakePlan:
        def __init__(self):
            self.status = "done"
            self.channel = "public"
            self.decided_at = None
            self.decided_by = ""

    class FakeRepo:
        async def get_by_content_id(self, session, content_id):
            return FakePlan()

    class FakeSession:
        async def flush(self):
            return None

    service = ps.PlanService.__new__(ps.PlanService)
    service.session = FakeSession()
    service.plan_repo = FakeRepo()

    result = await service.complete("n2", "")
    assert result["status"] == "closed"
    assert result["channel"] == "public"


async def test_complete_without_plan_creates_skip_plan(monkeypatch):
    """极少数无方案记录时，完成处理应补一条 skip 方案并直接关闭。"""
    from app_v2.services import plan_service as ps

    monkeypatch.setattr(ps, "to_dict", lambda row: {"status": row.status, "channel": row.channel})

    class FakePlan:
        def __init__(self):
            self.status = "pending"
            self.channel = "skip"
            self.decided_at = None
            self.decided_by = ""

    upserted = {}

    class FakeRepo:
        async def get_by_content_id(self, session, content_id):
            return None

        async def upsert(self, session, brand_id, content_id, trigger, plan):
            upserted["plan"] = plan
            return FakePlan()

    class FakeBrands:
        async def get_default(self, session):
            return type("B", (), {"id": "b1"})()

    class FakeSession:
        async def flush(self):
            return None

    service = ps.PlanService.__new__(ps.PlanService)
    service.session = FakeSession()
    service.plan_repo = FakeRepo()
    service.brands = FakeBrands()

    result = await service.complete("n3", "")
    assert upserted["plan"]["channel"] == "skip"
    assert result["status"] == "closed"
    assert result["channel"] == "skip"


async def test_complete_processing_plan_raises(monkeypatch):
    """方案还在生成中时不允许直接完成处理。"""
    from app_v2.services import plan_service as ps

    class FakePlan:
        status = "processing"
        channel = None

    class FakeRepo:
        async def get_by_content_id(self, session, content_id):
            return FakePlan()

    service = ps.PlanService.__new__(ps.PlanService)
    service.session = object()
    service.plan_repo = FakeRepo()

    import pytest as _pytest
    with _pytest.raises(ValueError):
        await service.complete("n4", "")


async def test_force_generation_skips_skipped_shortcircuit(monkeypatch):
    """手动强制生成时，即使"正面/中性 + 低风险"也必须真正产出方案（不再判暂不处理）。"""
    from app_v2.services import plan_service as ps
    from app_v2.services.workflows import planning_workflow as pw

    # 假 Agent 输出
    class FakeChannel:
        action = "public"
        reason = "误解类内容，公开回应即可"

    class FakeDraft:
        text = "您好，感谢反馈，我们会进一步核实处理"

    class FakeScore:
        score = 9
        passed = True
        feedback = "OK"
        dimension_scores = {"tone": 9, "fact": 9}

    async def fake_channel(p):
        return FakeChannel()
    async def fake_draft(p):
        return FakeDraft()
    async def fake_score(p):
        return FakeScore()
    monkeypatch.setattr(pw, "run_channel_agent", fake_channel)
    monkeypatch.setattr(pw, "run_draft_agent", fake_draft)
    monkeypatch.setattr(pw, "run_score_agent", fake_score)
    monkeypatch.setattr(ps, "to_dict", lambda row: {"status": row.status, "channel": row.channel, "comment_copy": row.comment_copy})

    upserted = {}

    class FakeNote:
        title = "测试"
        body = "内容"
        published_at = None

    class FakeAnalysis:
        sentiment = "正面"      # ← 正面
        risk_level = "低"        # ← 低风险（正常应被短路）
        summary = "无风险"
        content_id = "n2"
        # to_dict 打桩会读这些属性，补齐避免 AttributeError
        status = "done"
        channel = ""
        comment_copy = ""
        dm_copy = ""

    class FakeRepo:
        async def get_by_content_id(self, session, content_id):
            return None

        async def upsert(self, session, brand_id, content_id, trigger, plan):
            upserted["plan"] = plan
            return type("P", (), {"id": "p1"})

        async def mark_status(self, *a, **k):
            return None

    class FakeBrands:
        async def get_default(self, session):
            return type("B", (), {"id": "b1"})()

    class FakeContentRepo:
        async def get_by_external_id(self, session, content_id):
            return FakeNote()

        async def list_comments(self, session, content_id):
            return []

    class FakeAnalysisRepo:
        async def latest_for_content(self, session, content_id):
            return FakeAnalysis()

    service = ps.PlanService.__new__(ps.PlanService)
    service.session = object()
    service.plan_repo = FakeRepo()
    service.brands = FakeBrands()
    service.content_repo = FakeContentRepo()
    service.analysis_repo = FakeAnalysisRepo()

    # 手动 create → force=True → 必须真正生成（不走 skipped 短路）
    await service.schedule_generation("n2", force=True)

    assert "skip" not in upserted["plan"].get("channel", "")   # 不是"暂不处理"
    # 最终落库应包含渠道（走 ③④⑤ 生成路径）
    assert upserted["plan"].get("channel") in ("dm", "public")
