import pytest
from fastapi import HTTPException

from app.api import routes_admin
from app.api.routes_admin import PromptConfigUpdateRequest
from app.rag.generate.prompt_config_store import PromptRuntimeConfig
from app.settings import settings


def test_require_admin_api_key_rejects_missing_key():
    original_admin_key = settings.admin_api_key
    try:
        settings.admin_api_key = "secret"
        with pytest.raises(HTTPException) as exc:
            routes_admin._require_admin_api_key(None)
        assert exc.value.status_code == 401
    finally:
        settings.admin_api_key = original_admin_key


def test_admin_prompt_config_get_returns_effective_paths(monkeypatch):
    monkeypatch.setattr(
        routes_admin,
        "get_runtime_config",
        lambda: PromptRuntimeConfig(None, None, 0, None, None, None),
    )
    monkeypatch.setattr(
        routes_admin,
        "resolve_effective_paths",
        lambda cfg=None: (
            "prompts/system_persona_dimy.md",
            "prompts/answer_template_dimy.md",
            "env",
            "env",
        ),
    )
    monkeypatch.setattr(routes_admin, "_prompt_file_info", lambda path, label: (f"/abs/{path}", 123))

    resp = routes_admin.admin_get_prompt_config()
    assert resp.effective_system_persona_path == "prompts/system_persona_dimy.md"
    assert resp.effective_answer_template_path == "prompts/answer_template_dimy.md"
    assert resp.system_persona_source == "env"
    assert resp.answer_template_source == "env"


def test_admin_prompt_config_put_updates_paths(monkeypatch):
    captured = {}
    current_cfg = PromptRuntimeConfig(None, None, 0, None, None, None)

    monkeypatch.setattr(routes_admin, "get_runtime_config", lambda: current_cfg)
    monkeypatch.setattr(
        routes_admin,
        "resolve_effective_paths",
        lambda cfg=None: (
            cfg.system_persona_path or "prompts/system_persona.md",
            cfg.answer_template_path or "prompts/answer_template.md",
            "db" if cfg and cfg.system_persona_path else "default",
            "db" if cfg and cfg.answer_template_path else "default",
        ),
    )
    monkeypatch.setattr(routes_admin, "_prompt_file_info", lambda path, label: (f"/abs/{path}", 321))

    def _fake_upsert(*, system_persona_path, answer_template_path, updated_by, change_note):
        captured["system_persona_path"] = system_persona_path
        captured["answer_template_path"] = answer_template_path
        captured["updated_by"] = updated_by
        captured["change_note"] = change_note
        return PromptRuntimeConfig(
            system_persona_path=system_persona_path,
            answer_template_path=answer_template_path,
            version=1,
            updated_by=updated_by,
            change_note=change_note,
            updated_at=None,
        )

    monkeypatch.setattr(routes_admin, "upsert_runtime_config", _fake_upsert)

    resp = routes_admin.admin_update_prompt_config(
        PromptConfigUpdateRequest(
            system_persona_path="/app/prompts/system_persona_dimy.md",
            answer_template_path="/app/prompts/answer_template_dimy.md",
            updated_by="admin-cell",
            change_note="new profile",
        )
    )

    assert captured["system_persona_path"] == "/app/prompts/system_persona_dimy.md"
    assert captured["answer_template_path"] == "/app/prompts/answer_template_dimy.md"
    assert captured["updated_by"] == "admin-cell"
    assert captured["change_note"] == "new profile"
    assert resp.version == 1
