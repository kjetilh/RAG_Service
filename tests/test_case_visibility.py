import pytest
pytest.importorskip("fastapi")
from fastapi import HTTPException

from app.api import routes_chat, routes_interviews, routes_research
from app.rag.cases.loader import PlannerConfig, RagCase, RagCasesConfig
from app.rag.cases.visibility import configured_instance_case_ids, visible_case_ids
from app.settings import settings


@pytest.fixture(autouse=True)
def restore_visibility_settings():
    original = settings.instance_case_ids_json
    yield
    settings.instance_case_ids_json = original


def _cfg() -> RagCasesConfig:
    return RagCasesConfig(
        version=1,
        default_case="innovasjon",
        cases=[
            RagCase(
                case_id="dimy_docs",
                description="Docs",
                enabled=True,
                planner=PlannerConfig(docs_source_types=["haven_docs"], prompts_source_types=["dimy_prompts"]),
            ),
            RagCase(
                case_id="innovasjon",
                description="Innovasjon",
                enabled=True,
                planner=PlannerConfig(docs_source_types=["innovasjonsledelse"], prompts_source_types=[]),
            ),
            RagCase(
                case_id="innovasjon_intervjuer",
                description="Intervjuer",
                enabled=True,
                planner=PlannerConfig(docs_source_types=["innovasjon_intervju_transcript"], prompts_source_types=[]),
            ),
        ],
    )


def test_visible_case_ids_respect_instance_allowlist():
    settings.instance_case_ids_json = '["innovasjon","innovasjon_intervjuer"]'

    out = visible_case_ids(_cfg())

    assert out == {"innovasjon", "innovasjon_intervjuer"}


def test_configured_instance_case_ids_rejects_invalid_json():
    settings.instance_case_ids_json = '{"bad": true}'

    with pytest.raises(ValueError):
        configured_instance_case_ids()


def test_chat_list_cases_respects_allowlist(monkeypatch):
    settings.instance_case_ids_json = '["innovasjon"]'
    monkeypatch.setattr(routes_chat, "load_rag_cases", lambda _path: _cfg())
    monkeypatch.setattr(routes_chat, "_available_source_types", lambda: {"haven_docs", "innovasjonsledelse"})

    resp = routes_chat.list_cases()

    assert resp == {"cases": [{"case_id": "innovasjon", "description": "Innovasjon", "enabled": True}]}


def test_chat_query_rejects_case_not_available_on_instance(monkeypatch):
    settings.instance_case_ids_json = '["innovasjon"]'
    monkeypatch.setattr(routes_chat, "validate_model_profile", lambda _profile: None)
    monkeypatch.setattr(routes_chat, "load_rag_cases", lambda _path: _cfg())

    with pytest.raises(HTTPException) as exc:
        routes_chat._run_query(
            routes_chat.QueryRequest(
                query="hei",
                case_id="dimy_docs",
            )
        )
    assert exc.value.status_code == 404


def test_research_allowed_case_ids_respect_instance_allowlist(monkeypatch):
    settings.instance_case_ids_json = '["innovasjon","innovasjon_intervjuer"]'
    monkeypatch.setattr(routes_research, "load_rag_cases", lambda _path: _cfg())

    out = routes_research._allowed_case_ids(
        routes_research.ResearchIdentity(
            token="t",
            label="x",
            scopes=frozenset({"research:read"}),
            case_ids=frozenset({"dimy_docs", "innovasjon"}),
        )
    )

    assert out == {"innovasjon"}


def test_interviews_route_rejects_hidden_prompt_profile(monkeypatch):
    settings.instance_case_ids_json = '["innovasjon","innovasjon_intervjuer"]'
    monkeypatch.setattr(routes_interviews, "validate_model_profile", lambda _profile: None)
    monkeypatch.setattr(routes_interviews, "load_rag_cases", lambda _path: _cfg())

    with pytest.raises(HTTPException) as exc:
        routes_interviews.interviews_collective_summary(
            routes_interviews.CollectiveSummaryRequest(
                case_id="innovasjon_intervjuer",
                prompt_profile_case_id="dimy_docs",
                questions=[{"question_id": "Q1", "text": "Hva?"}],
            )
        )
    assert exc.value.status_code == 404
