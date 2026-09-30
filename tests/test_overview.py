"""总览页新增统计（趋势 + 最近预警）的回归测试。"""

import pytest
from datetime import datetime, timedelta, timezone


async def test_overview_trend_groups_by_day():
    """趋势图：按天聚合笔记数与中高风险数。"""
    from app_v2.services import analytics_service as ans

    # 用 naive UTC 时间模拟 MySQL 读回来的 created_at（无时区）
    now_naive = datetime.now(timezone.utc).replace(tzinfo=None)
    today = now_naive
    yesterday = now_naive - timedelta(days=1)

    class FakeResult:
        def all(self):
            return [
                (today, "高"),
                (today, "低"),
                (yesterday, "中"),
                (yesterday, "中"),
            ]

    class FakeSession:
        async def execute(self, stmt, *a, **k):
            return FakeResult()

    service = ans.AnalyticsService.__new__(ans.AnalyticsService)
    service.session = FakeSession()

    out = await service.overview_trend(days=7)
    assert len(out["items"]) == 7
    # 列表按旧→新排序：最后一项是今天，倒数第二项是昨天
    today_item = out["items"][-1]
    assert today_item["notes"] == 2
    assert today_item["medium_high"] == 1
    assert today_item["medium"] == 0
    assert today_item["high"] == 1
    yesterday_item = out["items"][-2]
    assert yesterday_item["notes"] == 2
    assert yesterday_item["medium_high"] == 2
    assert yesterday_item["medium"] == 2
    assert yesterday_item["high"] == 0


async def test_recent_pending_notes():
    """最近预警：返回中高风险未处理笔记的标题/情感/风险/原因。"""
    from app_v2.services import content_service as cs

    class FakeContent:
        def __init__(self, cid, title, author):
            self.content_id = cid
            self.title = title
            self.author = author
            self.created_at = None
            self.url = ""
            self.published_at = None

    class FakeAnalysis:
        def __init__(self, sentiment, risk, summary):
            self.sentiment = sentiment
            self.risk_level = risk
            self.summary = summary

    rows = [
        (FakeContent("c1", "冒烟了", "A"), FakeAnalysis("负面", "高", "涉及安全隐患")),
        (FakeContent("c2", "有点暗", "B"), FakeAnalysis("中性", "中", "亮度不够")),
    ]

    class FakeResult:
        def all(self):
            return rows

    class FakeSession:
        async def execute(self, stmt, *a, **k):
            return FakeResult()

    service = cs.ContentService.__new__(cs.ContentService)
    service.session = FakeSession()

    out = await service.recent_pending_notes(5)
    assert len(out) == 2
    assert out[0]["content_id"] == "c1"
    assert out[0]["risk_level"] == "高"
    assert out[0]["sentiment"] == "负面"
    assert out[0]["reason"] == "涉及安全隐患"
    assert out[1]["risk_level"] == "中"
