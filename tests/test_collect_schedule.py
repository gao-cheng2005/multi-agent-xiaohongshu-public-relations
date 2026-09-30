import pytest


async def test_collect_semaphores_exist():
    from app_v2.services.collect_service import _PLAN_SEMAPHORE, _TAG_SEMAPHORE

    # 方案生成与问题标签各有独立并发上限（稳定版调为 2，避免同批多篇时连接池压力过大）
    assert _PLAN_SEMAPHORE._value == 2
    assert _TAG_SEMAPHORE._value == 2


def test_schedule_plan_uses_independent_session():
    """后台生成方案必须自建独立会话（否则请求结束会话关闭，任务失败导致方案不自动生成）。"""
    from app_v2.services import collect_service as cs
    import inspect

    src = inspect.getsource(cs._schedule_plan)
    assert "SessionLocal" in src
    assert "PlanService(session)" in src


async def test_content_exists_checks_dedup_hash():
    """重复采集判断：按去重指纹判断笔记是否已入库。"""
    from app_v2.core.cleaning import dedup_hash
    from app_v2.services import data_access_service as das

    seen = []

    class FakeRepo:
        async def get_by_dedup_hash(self, session, h):
            seen.append(h)
            return None  # 未入库

    svc = das.DataAccessService.__new__(das.DataAccessService)
    svc.session = object()
    svc.content_repo = FakeRepo()

    url = "https://www.xiaohongshu.com/explore/abc123?xsec_token=xyz"
    assert await svc.content_exists({"url": url}) is False
    assert seen == [dedup_hash(url)]


async def test_search_new_notes_fills_up_after_skipping_duplicates():
    """关键词补采：第一次窗口里 2 条重复被跳过，凑够 wanted 条新笔记。"""
    from app_v2.services import collect_service as cs

    calls = []

    class FakeCollector:
        def search(self, keyword, limit):
            calls.append(limit)
            return [{"url": f"https://x.com/e/{i}", "title": f"n{i}"} for i in range(limit)]

    class FakeDataAccess:
        async def content_exists(self, content):
            return content["url"].endswith("/e/0") or content["url"].endswith("/e/1")

    svc = cs.CollectService.__new__(cs.CollectService)
    svc.session = object()
    svc.data_access = FakeDataAccess()

    contents, skipped = await svc._search_new_notes(FakeCollector(), "产品A", 3)
    assert len(contents) == 3
    assert skipped == 2
    # 一次窗口（10）就凑够了，不需要再搜
    assert calls == [10]
    urls = [c["url"] for c in contents]
    assert "https://x.com/e/0" not in urls
    assert "https://x.com/e/1" not in urls


async def test_search_new_notes_expands_window_when_all_duplicates():
    """关键词补采：第一个窗口全是重复时，放大窗口继续往深处补采。"""
    from app_v2.services import collect_service as cs

    calls = []

    class FakeCollector:
        def search(self, keyword, limit):
            calls.append(limit)
            return [{"url": f"https://x.com/e/{i}", "title": f"n{i}"} for i in range(limit)]

    class FakeDataAccess:
        async def content_exists(self, content):
            idx = int(content["url"].rsplit("/e/", 1)[1])
            return idx < 10  # 前 10 条已入库

    svc = cs.CollectService.__new__(cs.CollectService)
    svc.session = object()
    svc.data_access = FakeDataAccess()

    contents, skipped = await svc._search_new_notes(FakeCollector(), "产品A", 3)
    assert calls == [10, 20]
    assert len(contents) == 3
    assert skipped == 10
    assert [c["url"] for c in contents] == [
        "https://x.com/e/10",
        "https://x.com/e/11",
        "https://x.com/e/12",
    ]


async def test_analyze_and_alert_uses_two_agents(monkeypatch):
    from app_v2.services import data_access_service as das

    async def fake_sent(note):
        return {"sentiment": "负面", "confidence": 0.8, "model": "fake"}

    async def fake_risk(note, comments=None):
        return {
            "risk_level": "高", "summary": "实锤", "score": 8,
            "harm_score": 8, "spread_score": 6, "urgent": True, "model": "fake",
        }

    monkeypatch.setattr(das, "analyze_sentiment", fake_sent)
    monkeypatch.setattr(das, "analyze_risk", fake_risk)

    # 用假仓库替换落库，验证分析结果组装、不含非法字段
    seen = {}

    class FakeBrands:
        async def get_default(self, s):
            return type("B", (), {"id": "brand-1"})()

    class FakeAnalysisRepo:
        async def replace_for_content(self, s, brand_id, cid, analysis):
            seen["analysis"] = analysis
            return None

    class FakeAlertRepo:
        async def replace_for_content(self, s, brand_id, cid, alerts):
            seen["alerts"] = alerts
            return None

    class FakeSession:
        pass

    svc = das.DataAccessService.__new__(das.DataAccessService)
    svc.session = FakeSession()
    svc.brands = FakeBrands()
    svc.analysis_repo = FakeAnalysisRepo()
    svc.alert_repo = FakeAlertRepo()

    await svc.analyze_and_alert(
        {"title": "假货", "body": "全是假货别买", "url": "u"},
        "abc",
        comments=[{"content": "别买"}],
    )
    analysis = seen["analysis"]
    assert analysis["sentiment"] == "负面"
    assert analysis["risk_level"] == "高"
    # 不把非表字段塞进分析记录（harm_score 等不持久化）
    assert "harm_score" not in analysis
    # 预警会基于分析生成
    assert any(a["rule"] == "高风险内容" for a in seen["alerts"])


async def test_apply_analysis_filters_non_model_fields(monkeypatch):
    """落库分析时必须白名单过滤：harm_score 等多维中间量不能进 Analysis。"""
    from app_v2.services import data_access_service as das

    seen = {}

    class FakeBrands:
        async def get_default(self, s):
            return type("B", (), {"id": "b"})()

    class FakeAnalysisRepo:
        async def replace_for_content(self, s, brand_id, cid, analysis):
            seen["analysis"] = analysis
            return None

    class FakeAlertRepo:
        async def replace_for_content(self, s, brand_id, cid, alerts):
            seen["alerts"] = alerts
            return None

    class FakeSession:
        pass

    svc = das.DataAccessService.__new__(das.DataAccessService)
    svc.session = FakeSession()
    svc.brands = FakeBrands()
    svc.analysis_repo = FakeAnalysisRepo()
    svc.alert_repo = FakeAlertRepo()

    await svc.apply_analysis_and_alerts(
        {"title": "t", "body": "b"},
        "n1",
        {
            "sentiment": "负面",
            "risk_level": "高",
            "score": 8,
            "summary": "s",
            "harm_score": 9,      # 不被持久化
            "spread_score": 6,    # 不被持久化
            "urgent": True,       # 不被持久化
            "topics": [],
            "keywords": [],
            "model": "x+y",
        },
    )
    analysis = seen["analysis"]
    assert analysis["sentiment"] == "负面"
    assert "harm_score" not in analysis
    assert "spread_score" not in analysis
    assert "urgent" not in analysis
    assert any(a["rule"] == "高风险内容" for a in seen["alerts"])
