from pathlib import Path

import pytest

from app.rag.generate.persona import load_persona
from app.rag.generate.prompts import load_answer_template
from app.settings import settings


_PROMPT_KEYS = ["system_persona_path", "answer_template_path"]


@pytest.fixture(autouse=True)
def restore_prompt_settings():
    original = {k: getattr(settings, k) for k in _PROMPT_KEYS}
    yield
    for k, v in original.items():
        setattr(settings, k, v)


def test_load_persona_from_configured_path(tmp_path: Path):
    persona_file = tmp_path / "persona.md"
    persona_file.write_text("custom persona", encoding="utf-8")
    settings.system_persona_path = str(persona_file)

    assert load_persona() == "custom persona"


def test_load_answer_template_from_configured_path(tmp_path: Path):
    template_file = tmp_path / "template.md"
    template_file.write_text("custom template", encoding="utf-8")
    settings.answer_template_path = str(template_file)

    assert load_answer_template() == "custom template"


def test_missing_prompt_file_raises_error():
    settings.system_persona_path = "/tmp/does-not-exist-persona.md"

    with pytest.raises(FileNotFoundError):
        load_persona()


def test_load_persona_from_case_profile(tmp_path: Path):
    original_rag_cases_path = settings.rag_cases_path
    try:
        persona_file = tmp_path / "persona.md"
        template_file = tmp_path / "template.md"
        cases_file = tmp_path / "cases.yml"
        persona_file.write_text("case persona", encoding="utf-8")
        template_file.write_text("case template", encoding="utf-8")
        cases_file.write_text(
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
      system_persona_path: "{persona_file}"
      answer_template_path: "{template_file}"
""",
            encoding="utf-8",
        )
        settings.rag_cases_path = str(cases_file)
        assert load_persona(case_id="docs") == "case persona"
        assert load_answer_template(case_id="docs") == "case template"
    finally:
        settings.rag_cases_path = original_rag_cases_path
