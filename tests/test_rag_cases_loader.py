from pathlib import Path

import pytest

from app.rag.cases.loader import case_by_id, load_rag_cases


def _write(tmp_path: Path, text: str) -> Path:
    p = tmp_path / "cases.yml"
    p.write_text(text, encoding="utf-8")
    return p


def test_load_rag_cases_valid(tmp_path: Path):
    p = _write(
        tmp_path,
        """
version: 1
default_case: docs
cases:
  - case_id: docs
    planner:
      docs_source_types: ["haven_docs"]
      prompts_source_types: ["dimy_prompts"]
      docs_keywords: ["api"]
      prompt_keywords: ["prompt"]
      default_domain: docs
    retrieval:
      top_k_vector: 10
      top_k_lexical: 9
      top_k_final: 8
      max_chunks_per_doc: 2
    evaluation:
      min_citations: 1
      min_unique_docs: 1
      min_avg_score: 0.0
      enforce: false
""",
    )
    cfg = load_rag_cases(p)
    assert cfg.default_case == "docs"
    assert len(cfg.cases) == 1
    assert case_by_id(cfg, None).case_id == "docs"


def test_load_rag_cases_rejects_unknown_fields(tmp_path: Path):
    p = _write(
        tmp_path,
        """
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
    retrieval:
      top_k_vector: 10
      top_k_lexical: 10
      top_k_final: 10
      max_chunks_per_doc: 2
      unknown_field: true
    evaluation:
      min_citations: 1
      min_unique_docs: 1
      min_avg_score: 0.0
      enforce: false
""",
    )
    with pytest.raises(ValueError):
        load_rag_cases(p)


def test_load_rag_cases_rejects_duplicate_yaml_keys(tmp_path: Path):
    p = _write(
        tmp_path,
        """
version: 1
version: 2
default_case: docs
cases:
  - case_id: docs
    planner:
      docs_source_types: []
      prompts_source_types: []
      docs_keywords: []
      prompt_keywords: []
      default_domain: docs
""",
    )
    with pytest.raises(ValueError):
        load_rag_cases(p)


def test_load_rag_cases_requires_existing_default_case(tmp_path: Path):
    p = _write(
        tmp_path,
        """
version: 1
default_case: missing
cases:
  - case_id: docs
    planner:
      docs_source_types: []
      prompts_source_types: []
      docs_keywords: []
      prompt_keywords: []
      default_domain: docs
""",
    )
    with pytest.raises(ValueError):
        load_rag_cases(p)


def test_case_by_id_raises_for_missing_case(tmp_path: Path):
    p = _write(
        tmp_path,
        """
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
""",
    )
    cfg = load_rag_cases(p)
    with pytest.raises(ValueError):
        case_by_id(cfg, "unknown")


def test_load_rag_cases_accepts_prompt_profile(tmp_path: Path):
    p = _write(
        tmp_path,
        """
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
      system_persona_path: "prompts/system_persona_interview.md"
      answer_template_path: "prompts/answer_template_interview.md"
""",
    )
    cfg = load_rag_cases(p)
    assert cfg.cases[0].prompt_profile.system_persona_path == "prompts/system_persona_interview.md"
    assert cfg.cases[0].prompt_profile.answer_template_path == "prompts/answer_template_interview.md"


def test_repository_case_split_keeps_dimy_docs_and_dimy_prompts_separate():
    cfg = load_rag_cases(Path("config/rag_cases.yml"))
    docs_case = case_by_id(cfg, "dimy_docs")
    prompts_case = case_by_id(cfg, "dimy_prompts")

    assert "prompt_docs" not in docs_case.planner.docs_source_types
    assert prompts_case.planner.docs_source_types == ["prompt_docs"]
    assert prompts_case.planner.prompts_source_types == []
