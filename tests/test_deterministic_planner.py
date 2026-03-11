from pathlib import Path

import pytest

from app.rag.planner.deterministic import plan_query
from app.settings import settings


_SETTINGS_KEYS = [
    "next_gen_rag_enabled",
    "rag_cases_path",
    "query_router_enabled",
    "query_router_docs_source_types_json",
    "query_router_prompts_source_types_json",
    "query_router_docs_keywords_json",
    "query_router_prompts_keywords_json",
]


@pytest.fixture(autouse=True)
def _restore_settings():
    original = {k: getattr(settings, k) for k in _SETTINGS_KEYS}
    yield
    for k, v in original.items():
        setattr(settings, k, v)


def _write_cases(tmp_path: Path) -> Path:
    p = tmp_path / "cases.yml"
    p.write_text(
        """
version: 1
default_case: docs_case
cases:
  - case_id: docs_case
    planner:
      docs_source_types: ["haven_docs"]
      prompts_source_types: ["dimy_prompts"]
      docs_keywords: ["api", "kode"]
      prompt_keywords: ["prompt", "template"]
      default_domain: docs
    retrieval:
      top_k_vector: 8
      top_k_lexical: 7
      top_k_final: 6
      max_chunks_per_doc: 2
    evaluation:
      min_citations: 2
      min_unique_docs: 1
      min_avg_score: 0.0
      enforce: false
""",
        encoding="utf-8",
    )
    return p


def test_plan_query_next_gen_prompt_domain(tmp_path: Path):
    settings.next_gen_rag_enabled = True
    settings.rag_cases_path = str(_write_cases(tmp_path))

    result = plan_query("Lag en promptmal for system prompt", {})

    assert result.case_id == "docs_case"
    assert result.filters["source_type"] == ["dimy_prompts"]
    assert result.trace["planner_mode"] == "deterministic"
    assert result.trace["selected_domain"] == "prompts"
    assert result.trace["reason"] == "keyword_score"
    assert result.trace["retrieval"]["top_k_final"] == 6


def test_plan_query_next_gen_is_deterministic(tmp_path: Path):
    settings.next_gen_rag_enabled = True
    settings.rag_cases_path = str(_write_cases(tmp_path))

    a = plan_query("Hvordan virker api sync", {})
    b = plan_query("Hvordan virker api sync", {})

    assert a.filters == b.filters
    assert a.trace == b.trace
    assert a.prompt_instruction == b.prompt_instruction


def test_plan_query_explicit_source_type_has_priority(tmp_path: Path):
    settings.next_gen_rag_enabled = True
    settings.rag_cases_path = str(_write_cases(tmp_path))

    result = plan_query("prompt api", {"source_type": ["haven_docs"]})
    assert result.filters["source_type"] == ["haven_docs"]
    assert result.trace["reason"] == "explicit_source_type_filter"


def test_plan_query_legacy_mode_still_works():
    settings.next_gen_rag_enabled = False
    settings.query_router_enabled = True
    settings.query_router_docs_source_types_json = '["haven_docs"]'
    settings.query_router_prompts_source_types_json = '["dimy_prompts"]'
    settings.query_router_docs_keywords_json = '["api"]'
    settings.query_router_prompts_keywords_json = '["prompt"]'

    result = plan_query("prompt", {})
    assert result.trace["planner_mode"] == "legacy_router"
    assert result.trace["selected_case"] is None


def test_plan_query_dimy_prompts_prefers_prompt_domain_for_component_queries(tmp_path: Path):
    settings.next_gen_rag_enabled = True
    cases_path = tmp_path / "cases.yml"
    cases_path.write_text(
        """
version: 1
default_case: dimy_prompts
cases:
  - case_id: dimy_prompts
    planner:
      docs_source_types: ["prompt_docs"]
      prompts_source_types: ["dimy_prompts"]
      docs_keywords: ["guide", "oversikt", "referanse"]
      prompt_keywords: ["celle", "celler", "komponent", "komponenter", "arbeidsrom", "workspace", "sammensette", "konfigurasjon"]
      default_domain: prompts
    retrieval:
      top_k_vector: 8
      top_k_lexical: 7
      top_k_final: 6
      max_chunks_per_doc: 2
    evaluation:
      min_citations: 2
      min_unique_docs: 1
      min_avg_score: 0.0
      enforce: false
""",
        encoding="utf-8",
    )
    settings.rag_cases_path = str(cases_path)

    result = plan_query("Hvordan setter jeg sammen celler som komponenter i et arbeidsrom?", {"rag_case_id": "dimy_prompts"})

    assert result.case_id == "dimy_prompts"
    assert result.filters["source_type"] == ["dimy_prompts"]
    assert result.trace["selected_domain"] == "prompts"
