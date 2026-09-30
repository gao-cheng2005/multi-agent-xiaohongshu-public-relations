import pytest


async def test_run_risk_agent_raises_without_key(monkeypatch):
    # 清空大模型密钥 → configured 变 False → run_risk_agent 应抛 RuntimeError
    from app_v2.core.settings import settings
    monkeypatch.setattr(settings, "siliconflow_api_key", "")
    from app_v2.services.agents.factory import run_risk_agent
    with pytest.raises(RuntimeError):
        await run_risk_agent("payload")
