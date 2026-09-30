"""
大模型（硅基流动）运行时配置的测试。

覆盖：模型切换即时生效、会话重建、无 key 降级、精选清单校验。
"""
import pytest


async def test_gateway_active_model_defaults_to_settings():
    """未在设置页切换过模型时，活动模型名等于 .env 默认模型。"""
    from app_v2.core.llm import llm_gateway
    from app_v2.core.settings import settings

    assert llm_gateway.active_model == settings.siliconflow_default_model


async def test_gateway_set_active_model_rebuilds_session(monkeypatch):
    """切换模型后，同名会话必须重建（不能继续用旧模型的会话）。"""
    from app_v2.core.llm import llm_gateway
    from app_v2.core.settings import settings

    # 构造 ChatOpenAI 必须要非空 key，这里用假 key 侧载（不发起真实请求）
    monkeypatch.setattr(settings, "siliconflow_api_key", "sk-test")
    before_model = llm_gateway.active_model
    try:
        s1 = llm_gateway.chat_model("switch-test")
        llm_gateway.set_active_model("Qwen/Qwen2.5-72B-Instruct")
        s2 = llm_gateway.chat_model("switch-test")
        assert s2 is not s1
        assert llm_gateway.active_model == "Qwen/Qwen2.5-72B-Instruct"
    finally:
        # 恢复原模型，避免影响其它测试
        llm_gateway.set_active_model(before_model)


async def test_gateway_configured_false_without_key(monkeypatch):
    """没有硅基流动 key 时 configured 为 False（走规则兜底）。"""
    from app_v2.core.settings import settings

    monkeypatch.setattr(settings, "siliconflow_api_key", "")
    from app_v2.core.llm import llm_gateway

    assert llm_gateway.configured is False


async def test_llm_models_contains_default():
    """精选模型清单必须包含默认模型。"""
    from app_v2.core.settings import LLM_MODELS, settings

    ids = {mid for mid, _ in LLM_MODELS}
    assert settings.siliconflow_default_model in ids


async def test_llm_config_service_rejects_unknown_model():
    """设置不在精选清单里的模型应被拒绝。"""
    from app_v2.services.llm_config_service import LLMConfigService

    svc = LLMConfigService.__new__(LLMConfigService)
    with pytest.raises(ValueError):
        await svc.set_current_model("not-a-real-model")


async def test_llm_config_service_set_and_get_model(monkeypatch):
    """设置模型：校验通过→写入配置→gateway 立即生效；读取返回同一模型。"""
    from app_v2.core.llm import llm_gateway
    from app_v2.services.llm_config_service import LLMConfigService

    class FakeRow:
        config_value = "deepseek-ai/DeepSeek-V3"

    class FakeRepo:
        async def get(self, session, key):
            return FakeRow() if key == "llm_model" else None

        async def upsert(self, session, brand_id, key, value):
            return type("R", (), {"config_value": value, "id": "x", "brand_id": "b",
                                  "config_key": key, "created_at": None, "updated_at": None})()

    class FakeBrands:
        async def get_default(self, session):
            return type("B", (), {"id": "brand-1"})()

    svc = LLMConfigService.__new__(LLMConfigService)
    svc.session = None
    svc.repo = FakeRepo()
    svc.brands = FakeBrands()
    # to_dict 需要真实 ORM 对象，测试里直接打桩成固定字典（与 test_plan_service 同模式）
    monkeypatch.setattr(
        "app_v2.services.llm_config_service.to_dict",
        lambda row: {"config_key": "llm_model", "config_value": row.config_value},
    )

    # 直接读（命中仓库里的值）
    current = await svc.get_current_model()
    assert current == "deepseek-ai/DeepSeek-V3"

    # 切换并落库 + 通知 gateway
    before = llm_gateway.active_model
    payload = await svc.set_current_model("Qwen/Qwen2.5-7B-Instruct")
    assert payload["config_value"] == "Qwen/Qwen2.5-7B-Instruct"
    assert llm_gateway.active_model == "Qwen/Qwen2.5-7B-Instruct"
    llm_gateway.set_active_model(before)


async def test_llm_config_service_get_falls_back_to_default(monkeypatch):
    """库里没有 llm_model 记录时，get_current_model 返回 .env 默认模型。"""
    from app_v2.core.settings import settings
    from app_v2.services.llm_config_service import LLMConfigService

    class FakeRepo:
        async def get(self, session, key):
            return None

    svc = LLMConfigService.__new__(LLMConfigService)
    svc.session = None
    svc.repo = FakeRepo()
    assert await svc.get_current_model() == settings.siliconflow_default_model