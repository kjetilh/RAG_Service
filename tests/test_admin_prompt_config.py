import pytest
from fastapi import HTTPException

from app.api import routes_admin
from app.api.routes_admin import ApplyCasePromptProfileRequest, PromptConfigUpdateRequest
from app.rag.cases.loader import PlannerConfig, PromptProfileConfig, RagCase, RagCasesConfig
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


def test_admin_case_prompt_profiles_returns_case_summary(monkeypatch):
    monkeypatch.setattr(
        routes_admin,
        "get_runtime_config",
        lambda: PromptRuntimeConfig(None, None, 0, None, None, None),
    )
    monkeypatch.setattr(
        routes_admin,
        "load_rag_cases",
        lambda _path: RagCasesConfig(
            version=1,
            default_case="innovasjon_bokskriving",
            cases=[
                RagCase(
                    case_id="innovasjon_bokskriving",
                    description="bok",
                    enabled=True,
                    planner=PlannerConfig(),
                    prompt_profile=PromptProfileConfig(
                        system_persona_path="prompts/system_persona_bokskriving.md",
                        answer_template_path="prompts/answer_template_bokskriving.md",
                    ),
                )
            ],
        ),
    )
    monkeypatch.setattr(
        routes_admin,
        "resolve_effective_paths",
        lambda cfg=None, case_id=None: (
            "prompts/system_persona_bokskriving.md",
            "prompts/answer_template_bokskriving.md",
            "case",
            "case",
        ),
    )
    monkeypatch.setattr(routes_admin, "_prompt_file_info", lambda path, label: (f"/abs/{path}", 111))

    resp = routes_admin.admin_case_prompt_profiles()
    assert len(resp.cases) == 1
    assert resp.cases[0].case_id == "innovasjon_bokskriving"
    assert resp.cases[0].system_persona_source == "case"


def test_admin_case_prompt_profiles_hide_cases_not_available_on_instance(monkeypatch):
    original_instance_json = settings.instance_case_ids_json
    settings.instance_case_ids_json = '["innovasjon_intervjuer"]'
    try:
        monkeypatch.setattr(
            routes_admin,
            "get_runtime_config",
            lambda: PromptRuntimeConfig(None, None, 0, None, None, None),
        )
        monkeypatch.setattr(
            routes_admin,
            "load_rag_cases",
            lambda _path: RagCasesConfig(
                version=1,
                default_case="innovasjon_intervjuer",
                cases=[
                    RagCase(
                        case_id="innovasjon_intervjuer",
                        description="intervju",
                        enabled=True,
                        planner=PlannerConfig(),
                        prompt_profile=PromptProfileConfig(
                            system_persona_path="prompts/system_persona_interview.md",
                            answer_template_path="prompts/answer_template_interview.md",
                        ),
                    ),
                    RagCase(
                        case_id="dimy_docs",
                        description="docs",
                        enabled=True,
                        planner=PlannerConfig(),
                        prompt_profile=PromptProfileConfig(
                            system_persona_path="prompts/system_persona_dimy.md",
                            answer_template_path="prompts/answer_template_dimy.md",
                        ),
                    ),
                ],
            ),
        )
        monkeypatch.setattr(
            routes_admin,
            "resolve_effective_paths",
            lambda cfg=None, case_id=None: (
                "prompts/system_persona_interview.md",
                "prompts/answer_template_interview.md",
                "case",
                "case",
            ),
        )
        monkeypatch.setattr(routes_admin, "_prompt_file_info", lambda path, label: (f"/abs/{path}", 111))

        resp = routes_admin.admin_case_prompt_profiles()
        assert [case.case_id for case in resp.cases] == ["innovasjon_intervjuer"]
    finally:
        settings.instance_case_ids_json = original_instance_json


def test_admin_apply_case_prompt_profile_uses_case_prompt_paths(monkeypatch):
    captured = {}
    monkeypatch.setattr(
        routes_admin,
        "load_rag_cases",
        lambda _path: RagCasesConfig(
            version=1,
            default_case="innovasjon_intervjuer",
            cases=[
                RagCase(
                    case_id="innovasjon_intervjuer",
                    description="intervju",
                    enabled=True,
                    planner=PlannerConfig(),
                    prompt_profile=PromptProfileConfig(
                        system_persona_path="prompts/system_persona_interview.md",
                        answer_template_path="prompts/answer_template_interview.md",
                    ),
                )
            ],
        ),
    )
    monkeypatch.setattr(
        routes_admin,
        "resolve_effective_paths",
        lambda cfg=None, case_id=None: (
            cfg.system_persona_path or "prompts/system_persona.md",
            cfg.answer_template_path or "prompts/answer_template.md",
            "db" if cfg and cfg.system_persona_path else "default",
            "db" if cfg and cfg.answer_template_path else "default",
        ),
    )
    monkeypatch.setattr(routes_admin, "_prompt_file_info", lambda path, label: (f"/abs/{path}", 222))

    def _fake_upsert(*, system_persona_path, answer_template_path, updated_by, change_note):
        captured["system_persona_path"] = system_persona_path
        captured["answer_template_path"] = answer_template_path
        captured["updated_by"] = updated_by
        captured["change_note"] = change_note
        return PromptRuntimeConfig(
            system_persona_path=system_persona_path,
            answer_template_path=answer_template_path,
            version=2,
            updated_by=updated_by,
            change_note=change_note,
            updated_at=None,
        )

    monkeypatch.setattr(routes_admin, "upsert_runtime_config", _fake_upsert)

    resp = routes_admin.admin_apply_case_prompt_profile(
        ApplyCasePromptProfileRequest(case_id="innovasjon_intervjuer", updated_by="ui")
    )
    assert captured["system_persona_path"] == "prompts/system_persona_interview.md"
    assert captured["answer_template_path"] == "prompts/answer_template_interview.md"
    assert resp.effective_system_persona_path == "prompts/system_persona_interview.md"


def test_admin_apply_case_prompt_profile_hides_case_not_available_on_instance(monkeypatch):
    original_instance_json = settings.instance_case_ids_json
    settings.instance_case_ids_json = '["innovasjon_intervjuer"]'
    try:
        monkeypatch.setattr(
            routes_admin,
            "load_rag_cases",
            lambda _path: RagCasesConfig(
                version=1,
                default_case="innovasjon_intervjuer",
                cases=[
                    RagCase(
                        case_id="innovasjon_intervjuer",
                        description="intervju",
                        enabled=True,
                        planner=PlannerConfig(),
                        prompt_profile=PromptProfileConfig(),
                    ),
                    RagCase(
                        case_id="dimy_docs",
                        description="docs",
                        enabled=True,
                        planner=PlannerConfig(),
                        prompt_profile=PromptProfileConfig(),
                    ),
                ],
            ),
        )

        with pytest.raises(HTTPException) as exc:
            routes_admin.admin_apply_case_prompt_profile(ApplyCasePromptProfileRequest(case_id="dimy_docs"))
        assert exc.value.status_code == 404
    finally:
        settings.instance_case_ids_json = original_instance_json
