import pytest

from app.rag.generate.llm_provider import (
    ModelProfileError,
    OpenAICompatibleProvider,
    default_provider,
)
from app.settings import settings


_SETTINGS_KEYS = [
    "llm_provider",
    "llm_base_url",
    "llm_api_key",
    "llm_model",
    "llm_profiles_json",
]


@pytest.fixture(autouse=True)
def restore_llm_settings():
    original = {k: getattr(settings, k) for k in _SETTINGS_KEYS}
    yield
    for k, v in original.items():
        setattr(settings, k, v)


def test_default_provider_uses_base_settings():
    settings.llm_provider = "openai_compat"
    settings.llm_base_url = "https://default.example/v1"
    settings.llm_api_key = "default-key"
    settings.llm_model = "default-model"
    settings.llm_profiles_json = ""

    provider = default_provider()
    assert isinstance(provider, OpenAICompatibleProvider)
    assert provider.base_url == "https://default.example/v1"
    assert provider.api_key == "default-key"
    assert provider.model == "default-model"


def test_unknown_model_profile_returns_client_error():
    settings.llm_profiles_json = '{"known":{"provider":"openai_compat","model":"m1"}}'
    with pytest.raises(ModelProfileError):
        default_provider("missing")


def test_model_profile_can_use_api_key_from_env(monkeypatch: pytest.MonkeyPatch):
    settings.llm_provider = "openai_compat"
    settings.llm_base_url = "https://default.example/v1"
    settings.llm_api_key = "default-key"
    settings.llm_model = "default-model"
    settings.llm_profiles_json = (
        '{"fast":{"base_url":"https://fast.example/v1","model":"fast-model","api_key_env":"FAST_KEY"}}'
    )
    monkeypatch.setenv("FAST_KEY", "env-key")

    provider = default_provider("fast")
    assert isinstance(provider, OpenAICompatibleProvider)
    assert provider.base_url == "https://fast.example/v1"
    assert provider.api_key == "env-key"
    assert provider.model == "fast-model"
