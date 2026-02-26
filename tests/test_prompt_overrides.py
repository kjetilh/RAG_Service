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
