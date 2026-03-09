from app.rag.generate.prompt_config_store import (
    PromptRuntimeConfig,
    resolve_effective_paths,
    resolve_prompt_path,
)
from app.settings import settings


def test_resolve_effective_paths_prefers_db_overrides():
    cfg = PromptRuntimeConfig(
        system_persona_path="prompts/system_persona_dimy.md",
        answer_template_path="prompts/answer_template_dimy.md",
        version=2,
        updated_by="tester",
        change_note="override",
        updated_at=None,
    )

    system_path, answer_path, system_source, answer_source = resolve_effective_paths(cfg)
    assert system_path == "prompts/system_persona_dimy.md"
    assert answer_path == "prompts/answer_template_dimy.md"
    assert system_source == "db"
    assert answer_source == "db"


def test_resolve_effective_paths_falls_back_to_env_values():
    original_system = settings.system_persona_path
    original_answer = settings.answer_template_path
    try:
        settings.system_persona_path = "/tmp/custom_system.md"
        settings.answer_template_path = "/tmp/custom_template.md"
        cfg = PromptRuntimeConfig(None, None, 0, None, None, None)

        system_path, answer_path, system_source, answer_source = resolve_effective_paths(cfg)
        assert system_path == "/tmp/custom_system.md"
        assert answer_path == "/tmp/custom_template.md"
        assert system_source == "env"
        assert answer_source == "env"
    finally:
        settings.system_persona_path = original_system
        settings.answer_template_path = original_answer


def test_resolve_prompt_path_handles_repo_relative_input():
    resolved = resolve_prompt_path("prompts/system_persona.md")
    assert resolved.is_absolute()
    assert str(resolved).endswith("/prompts/system_persona.md")


def test_resolve_effective_paths_prefers_case_profile_over_db_and_env(tmp_path):
    original_rag_cases_path = settings.rag_cases_path
    original_system = settings.system_persona_path
    original_answer = settings.answer_template_path
    try:
        persona = tmp_path / "case_persona.md"
        template = tmp_path / "case_template.md"
        persona.write_text("case persona", encoding="utf-8")
        template.write_text("case template", encoding="utf-8")
        cases = tmp_path / "cases.yml"
        cases.write_text(
            f"""
version: 1
default_case: docs
cases:
  - case_id: docs
    planner:
      docs_source_types: []
      prompts_source_types: []
      docs_keywords: []
      prompt_keywords: []
      default_domain: docs
    prompt_profile:
      system_persona_path: "{persona}"
      answer_template_path: "{template}"
""",
            encoding="utf-8",
        )
        settings.rag_cases_path = str(cases)
        settings.system_persona_path = "/tmp/env_system.md"
        settings.answer_template_path = "/tmp/env_answer.md"
        runtime_cfg = PromptRuntimeConfig(
            system_persona_path="/tmp/db_system.md",
            answer_template_path="/tmp/db_answer.md",
            version=1,
            updated_by="tester",
            change_note=None,
            updated_at=None,
        )

        system_path, answer_path, system_source, answer_source = resolve_effective_paths(runtime_cfg, case_id="docs")
        assert system_path == str(persona)
        assert answer_path == str(template)
        assert system_source == "case"
        assert answer_source == "case"
    finally:
        settings.rag_cases_path = original_rag_cases_path
        settings.system_persona_path = original_system
        settings.answer_template_path = original_answer
