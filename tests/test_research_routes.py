import json
from pathlib import Path

import pytest
from fastapi import HTTPException
from fastapi.responses import FileResponse

from app.api import routes_research
from app.models.schemas import Citation, QueryResponse
from app.rag.cases.loader import PlannerConfig, RagCase, RagCasesConfig
from app.settings import settings


@pytest.fixture(autouse=True)
def restore_research_settings():
    original_tokens = settings.research_api_tokens_json
    original_rag_cases_path = settings.rag_cases_path
    original_signing_key = settings.research_download_signing_key
    original_download_ttl = settings.research_download_ttl_seconds
    yield
    settings.research_api_tokens_json = original_tokens
    settings.rag_cases_path = original_rag_cases_path
    settings.research_download_signing_key = original_signing_key
    settings.research_download_ttl_seconds = original_download_ttl


def _identity(*scopes: str, case_ids: list[str] | None = None, token: str = "tok") -> routes_research.ResearchIdentity:
    return routes_research.ResearchIdentity(
        token=token,
        label="test",
        scopes=frozenset(scopes),
        case_ids=(frozenset(case_ids) if case_ids else None),
    )


def test_resolve_research_identity_accepts_bearer_and_query_token():
    settings.research_api_tokens_json = json.dumps(
        {
            "research-token": {
                "label": "deep-research",
                "scopes": ["research:read", "research:download"],
                "case_ids": ["doc_case"],
            }
        }
    )

    ident = routes_research._resolve_research_identity(authorization="Bearer research-token", access_token=None)
    assert ident.label == "deep-research"
    assert "research:download" in ident.scopes
    assert ident.case_ids == frozenset({"doc_case"})

    ident_from_query = routes_research._resolve_research_identity(authorization=None, access_token="research-token")
    assert ident_from_query.token == "research-token"


def test_research_cases_filters_to_allowed_enabled_cases(monkeypatch):
    monkeypatch.setattr(
        routes_research,
        "load_rag_cases",
        lambda _path: RagCasesConfig(
            version=1,
            default_case="doc_case",
            cases=[
                RagCase(case_id="doc_case", description="Docs", enabled=True, planner=PlannerConfig()),
                RagCase(case_id="prompt_case", description="Prompts", enabled=True, planner=PlannerConfig()),
                RagCase(case_id="disabled_case", description="Disabled", enabled=False, planner=PlannerConfig()),
            ],
        ),
    )

    resp = routes_research.research_cases(identity=_identity("research:read", case_ids=["doc_case"]))
    assert [case.case_id for case in resp.cases] == ["doc_case"]


def test_research_query_rewrites_download_urls_with_signed_grant(monkeypatch):
    monkeypatch.setattr(routes_research, "_require_case_access", lambda *_args: None)
    monkeypatch.setattr(routes_research.time, "time", lambda: 1_700_000_000)
    settings.research_download_signing_key = "signing-secret"
    settings.research_download_ttl_seconds = 120

    def _fake_run(req):
        assert req.case_id == "doc_case"
        assert req.prompt_profile_case_id == "prompt_case"
        return QueryResponse(
            answer="ok",
            citations=[
                Citation(doc_id="d1", title="Doc", chunk_id="c1", score=0.9, excerpt="x", download_url="/v1/documents/d1/download")
            ],
            retrieval_debug={"query_plan": {"selected_case": "doc_case"}},
            trace=None,
        )

    monkeypatch.setattr(routes_research, "_run_query", _fake_run)

    resp = routes_research.research_query(
        routes_research.ResearchQueryRequest(
            case_id="doc_case",
            query="What changed?",
            prompt_profile_case_id="prompt_case",
        ),
        identity=_identity("research:read", "research:download", case_ids=["doc_case"], token="secret-token"),
    )
    assert resp.trace == {"selected_case": "doc_case"}
    expected_sig = routes_research._download_signature("d1", 1_700_000_120, "doc_case")
    assert (
        resp.citations[0].download_url
        == f"/v1/research/documents/d1/download?exp=1700000120&cases=doc_case&sig={expected_sig}"
    )


def test_research_query_falls_back_to_access_token_when_signing_key_missing(monkeypatch):
    monkeypatch.setattr(routes_research, "_require_case_access", lambda *_args: None)

    def _fake_run(req):
        assert req.case_id == "doc_case"
        return QueryResponse(
            answer="ok",
            citations=[
                Citation(doc_id="d1", title="Doc", chunk_id="c1", score=0.9, excerpt="x", download_url="/v1/documents/d1/download")
            ],
            retrieval_debug={"query_plan": {"selected_case": "doc_case"}},
            trace=None,
        )

    monkeypatch.setattr(routes_research, "_run_query", _fake_run)

    resp = routes_research.research_query(
        routes_research.ResearchQueryRequest(case_id="doc_case", query="What changed?"),
        identity=_identity("research:read", "research:download", case_ids=["doc_case"], token="secret-token"),
    )
    assert resp.citations[0].download_url == "/v1/research/documents/d1/download?access_token=secret-token"


def test_research_query_omits_download_url_without_download_scope(monkeypatch):
    monkeypatch.setattr(routes_research, "_require_case_access", lambda *_args: None)
    monkeypatch.setattr(
        routes_research,
        "_run_query",
        lambda _req: QueryResponse(
            answer="ok",
            citations=[Citation(doc_id="d1", title="Doc", chunk_id="c1", score=0.9, excerpt="x")],
            retrieval_debug=None,
            trace=None,
        ),
    )

    resp = routes_research.research_query(
        routes_research.ResearchQueryRequest(case_id="doc_case", query="What changed?"),
        identity=_identity("research:read", case_ids=["doc_case"]),
    )
    assert resp.citations[0].download_url is None


def test_require_document_access_checks_allowed_case_intersection(monkeypatch):
    monkeypatch.setattr(routes_research, "_document_case_ids", lambda _doc_id: {"prompt_case"})

    with pytest.raises(HTTPException) as exc:
        routes_research._require_document_access("d1", _identity("research:download", case_ids=["doc_case"]))
    assert exc.value.status_code == 404


def test_require_case_access_hides_case_not_available_on_instance(monkeypatch):
    monkeypatch.setattr(routes_research, "case_exists", lambda _case_id: True)
    monkeypatch.setattr(routes_research, "_allowed_case_ids", lambda _identity: {"dimy_docs"})

    with pytest.raises(HTTPException) as exc:
        routes_research._require_case_access("innovasjon", _identity("research:read", case_ids=["innovasjon"]))
    assert exc.value.status_code == 404


def test_research_download_document_returns_file_response(tmp_path: Path, monkeypatch):
    doc_path = tmp_path / "doc.md"
    doc_path.write_text("# hello", encoding="utf-8")

    monkeypatch.setattr(routes_research, "_require_document_access", lambda *_args: None)
    monkeypatch.setattr(routes_research, "_document_file_path", lambda _doc_id: str(doc_path))
    monkeypatch.setattr(routes_research, "_resolve_download_path", lambda stored: Path(stored))

    response = routes_research.research_download_document(
        "d1",
        identity=_identity("research:download", case_ids=["doc_case"]),
    )
    assert isinstance(response, FileResponse)
    assert response.path == str(doc_path)


def test_research_download_document_accepts_signed_grant(tmp_path: Path, monkeypatch):
    doc_path = tmp_path / "doc.md"
    doc_path.write_text("# hello", encoding="utf-8")
    settings.research_download_signing_key = "signing-secret"
    monkeypatch.setattr(routes_research.time, "time", lambda: 1_700_000_000)
    monkeypatch.setattr(routes_research, "_document_case_ids", lambda _doc_id: {"doc_case"})
    monkeypatch.setattr(routes_research, "_document_file_path", lambda _doc_id: str(doc_path))
    monkeypatch.setattr(routes_research, "_resolve_download_path", lambda stored: Path(stored))

    grant = routes_research.SignedDownloadGrant(
        exp=1_700_000_120,
        cases="doc_case",
        sig=routes_research._download_signature("d1", 1_700_000_120, "doc_case"),
    )

    response = routes_research.research_download_document(
        "d1",
        exp=grant.expires_at,
        cases=grant.case_scope,
        sig=grant.signature,
        identity=None,
    )
    assert isinstance(response, FileResponse)
    assert response.path == str(doc_path)


def test_research_download_document_rejects_expired_signed_grant(monkeypatch):
    settings.research_download_signing_key = "signing-secret"
    monkeypatch.setattr(routes_research.time, "time", lambda: 1_700_000_500)

    with pytest.raises(HTTPException) as exc:
        routes_research._require_signed_download_access(
            "d1",
            routes_research.SignedDownloadGrant(
                exp=1_700_000_120,
                cases="doc_case",
                sig=routes_research._download_signature("d1", 1_700_000_120, "doc_case"),
            ),
        )
    assert exc.value.status_code == 401


def test_research_download_document_rejects_case_mismatch_for_signed_grant(monkeypatch):
    settings.research_download_signing_key = "signing-secret"
    monkeypatch.setattr(routes_research.time, "time", lambda: 1_700_000_000)
    monkeypatch.setattr(routes_research, "_document_case_ids", lambda _doc_id: {"prompt_case"})

    with pytest.raises(HTTPException) as exc:
        routes_research._require_signed_download_access(
            "d1",
            routes_research.SignedDownloadGrant(
                exp=1_700_000_120,
                cases="doc_case",
                sig=routes_research._download_signature("d1", 1_700_000_120, "doc_case"),
            ),
        )
    assert exc.value.status_code == 404
