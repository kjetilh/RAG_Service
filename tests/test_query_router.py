import pytest

from app.rag.retrieve.query_router import route_query, router_prompt_instruction
from app.settings import settings


_ROUTER_KEYS = [
    "query_router_enabled",
    "query_router_docs_source_types_json",
    "query_router_prompts_source_types_json",
    "query_router_docs_keywords_json",
    "query_router_prompts_keywords_json",
]


@pytest.fixture(autouse=True)
def restore_router_settings():
    original = {k: getattr(settings, k) for k in _ROUTER_KEYS}
    yield
    for k, v in original.items():
        setattr(settings, k, v)


def test_route_query_disabled_returns_original_filters():
    settings.query_router_enabled = False
    filters = {"source_type": ["custom_docs"]}

    out_filters, plan = route_query("Hei", filters)
    assert out_filters == filters
    assert plan["router_enabled"] is False


def test_route_query_routes_to_prompts_on_keyword():
    settings.query_router_enabled = True
    settings.query_router_docs_source_types_json = '["haven_docs"]'
    settings.query_router_prompts_source_types_json = '["dimy_prompts"]'
    settings.query_router_docs_keywords_json = '["api","kode"]'
    settings.query_router_prompts_keywords_json = '["prompt","template"]'

    out_filters, plan = route_query("Kan du forbedre denne prompten?", {})
    assert out_filters["source_type"] == ["dimy_prompts"]
    assert plan["selected_domain"] == "prompts"
    assert plan["reason"] == "keyword_score"
    assert plan["prompt_keyword_hits"] > plan["docs_keyword_hits"]
    assert "prompt" in plan["matched_prompt_keywords"]
    assert router_prompt_instruction(plan) is not None


def test_route_query_defaults_to_docs_when_no_keywords():
    settings.query_router_enabled = True
    settings.query_router_docs_source_types_json = '["haven_docs","cellprotocol_docs"]'
    settings.query_router_prompts_source_types_json = '["dimy_prompts"]'
    settings.query_router_docs_keywords_json = '["api","kode"]'
    settings.query_router_prompts_keywords_json = '["prompt"]'

    out_filters, plan = route_query("Hvordan virker replay flow i praksis", {})
    assert out_filters["source_type"] == ["haven_docs", "cellprotocol_docs"]
    assert plan["selected_domain"] == "docs"
    assert plan["reason"] == "default_domain"


def test_route_query_routes_to_docs_on_docs_keyword():
    settings.query_router_enabled = True
    settings.query_router_docs_source_types_json = '["haven_docs"]'
    settings.query_router_prompts_source_types_json = '["dimy_prompts"]'
    settings.query_router_docs_keywords_json = '["api","kode"]'
    settings.query_router_prompts_keywords_json = '["prompt"]'

    out_filters, plan = route_query("Hvilket API-endepunkt brukes for sync", {})
    assert out_filters["source_type"] == ["haven_docs"]
    assert plan["selected_domain"] == "docs"
    assert plan["reason"] == "keyword_score"
    assert "api" in plan["matched_docs_keywords"]


def test_route_query_keyword_tie_defaults_to_docs():
    settings.query_router_enabled = True
    settings.query_router_docs_source_types_json = '["haven_docs"]'
    settings.query_router_prompts_source_types_json = '["dimy_prompts"]'
    settings.query_router_docs_keywords_json = '["api"]'
    settings.query_router_prompts_keywords_json = '["prompt"]'

    out_filters, plan = route_query("Lag prompt for API-kall", {})
    assert out_filters["source_type"] == ["haven_docs"]
    assert plan["selected_domain"] == "docs"
    assert plan["reason"] == "keyword_tie_defaults_docs"
