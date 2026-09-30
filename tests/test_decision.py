from datetime import datetime, timezone, timedelta
from app_v2.services.agents.decision import (
    should_generate, score_passed, is_stale_processing,
)


def test_should_generate_skip_cases():
    # 正面/中性 + 低风险 → 暂不处理
    assert should_generate("正面", "低") is False
    assert should_generate("中性", "低") is False
    # 其余情况都要生成
    assert should_generate("负面", "低") is True
    assert should_generate("中性", "中") is True
    assert should_generate("正面", "高") is True


def test_score_passed():
    assert score_passed(9, {"tone": 9, "fact": 9}) is True
    assert score_passed(8.5, {"tone": 6, "fact": 9}) is True
    assert score_passed(7.5, {"tone": 9, "fact": 9}) is False   # 总分 <8
    assert score_passed(8.5, {"tone": 5, "fact": 9}) is False   # 单项=5 不合格


def test_is_stale_processing():
    now = datetime.now(timezone.utc)
    old = now - timedelta(minutes=15)
    fresh = now - timedelta(minutes=1)
    assert is_stale_processing(old, now) is True
    assert is_stale_processing(fresh, now) is False
    assert is_stale_processing(None, now) is False
