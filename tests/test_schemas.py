import pytest
from pydantic import ValidationError
from app_v2.models.schemas import (
    NoteSentiment, RiskResult, ChannelResult, DraftResult, ScoreResult,
)


def test_channel_action_enum():
    assert ChannelResult(action="dm", reason="实锤指控").action == "dm"
    assert ChannelResult(action="public", reason="误解类内容").action == "public"
    assert ChannelResult(action="skip", reason="无需处理").action == "skip"
    with pytest.raises(ValidationError):
        ChannelResult(action="神秘操作", reason="x")


def test_risk_result():
    r = RiskResult(risk_level="中", reason="评论区出现投诉", harm_score=7, spread_score=5, urgent=True)
    assert r.risk_level == "中" and r.urgent is True


def test_score_result_passed():
    s = ScoreResult(score=9, passed=True, feedback="语气可再缓和")
    assert s.passed is True


def test_note_sentiment():
    n = NoteSentiment(sentiment="负面", confidence=0.9)
    assert n.sentiment == "负面"


def test_draft_result():
    d = DraftResult(text="请联系官方客服核实处理")
    assert "官方" in d.text
