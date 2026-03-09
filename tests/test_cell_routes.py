import pytest
from fastapi import HTTPException

from app.api import routes_cell
from app.models.schemas import ChatResponse, Citation, QueryRequest
from app.rag.access.control import CaseMember
from app.rag.interviews.collective import InterviewQuestion, PreparedQuestionSet
from app.settings import settings


@pytest.fixture(autouse=True)
def restore_cell_settings():
    original_enabled = settings.cell_access_control_enabled
    original_secret = settings.cell_gateway_shared_secret
    original_admin_key = settings.admin_api_key
    yield
    settings.cell_access_control_enabled = original_enabled
    settings.cell_gateway_shared_secret = original_secret
    settings.admin_api_key = original_admin_key


def test_resolve_identity_requires_secret_when_enabled():
    settings.cell_access_control_enabled = True
    settings.cell_gateway_shared_secret = "shared-secret"

    with pytest.raises(HTTPException) as exc:
        routes_cell._resolve_identity(
            x_api_key=None,
            x_cell_gateway_secret=None,
            x_cell_user_id="u1",
        )
    assert exc.value.status_code == 401

    ident = routes_cell._resolve_identity(
        x_api_key=None,
        x_cell_gateway_secret="shared-secret",
        x_cell_user_id="u1",
    )
    assert ident.user_id == "u1"
    assert ident.via_admin_api_key is False


def test_cell_cases_filters_unassigned_cases_when_enabled(monkeypatch):
    settings.cell_access_control_enabled = True
    monkeypatch.setattr(
        routes_cell,
        "case_list_for_user",
        lambda _uid: [
            {"case_id": "dimy_docs", "description": "docs", "enabled": True, "role": "viewer"},
            {"case_id": "innovasjon", "description": "inn", "enabled": True, "role": None},
        ],
    )

    resp = routes_cell.cell_cases(identity=routes_cell.CellIdentity(user_id="u1"))
    assert [c.case_id for c in resp.cases] == ["dimy_docs"]

    admin_resp = routes_cell.cell_cases(identity=routes_cell.CellIdentity(user_id="u1", via_admin_api_key=True))
    assert [c.case_id for c in admin_resp.cases] == ["dimy_docs", "innovasjon"]


def test_cell_query_enforces_viewer_role(monkeypatch):
    settings.cell_access_control_enabled = True
    monkeypatch.setattr(routes_cell, "case_exists", lambda _case_id: True)
    monkeypatch.setattr(routes_cell, "has_case_role", lambda *_args: False)

    with pytest.raises(HTTPException) as exc:
        routes_cell.cell_query(
            "dimy_docs",
            QueryRequest(query="hello"),
            identity=routes_cell.CellIdentity(user_id="u2"),
        )
    assert exc.value.status_code == 403


def test_cell_query_sets_case_id_and_returns_trace(monkeypatch):
    settings.cell_access_control_enabled = True
    monkeypatch.setattr(routes_cell, "case_exists", lambda _case_id: True)
    monkeypatch.setattr(routes_cell, "has_case_role", lambda *_args: True)
    monkeypatch.setattr(routes_cell, "resolve_case_role", lambda *_args: "viewer")

    captured = {}

    def _fake_run(req: QueryRequest):
        captured["case_id"] = req.case_id
        captured["filters"] = req.filters
        captured["prompt_profile_case_id"] = req.prompt_profile_case_id
        return ChatResponse(
            answer="ok",
            citations=[Citation(doc_id="d1", title="t", chunk_id="c1", score=0.8, excerpt="x")],
            retrieval_debug={"query_plan": {"selected_case": "dimy_docs"}},
        )

    monkeypatch.setattr(routes_cell, "_run_query", _fake_run)

    resp = routes_cell.cell_query(
        "dimy_docs",
        QueryRequest(
            query="hello",
            filters={"source_type": ["haven_docs"]},
            prompt_profile_case_id="innovasjon_intervjuer",
        ),
        identity=routes_cell.CellIdentity(user_id="u2"),
    )
    assert captured["case_id"] == "dimy_docs"
    assert captured["filters"]["source_type"] == ["haven_docs"]
    assert captured["prompt_profile_case_id"] == "innovasjon_intervjuer"
    assert resp.trace["selected_case"] == "dimy_docs"


def test_member_upsert_requires_owner_or_admin_key(monkeypatch):
    settings.cell_access_control_enabled = True
    monkeypatch.setattr(routes_cell, "_require_known_case", lambda _case_id: None)
    monkeypatch.setattr(routes_cell, "_actor_role", lambda *_args: "admin")

    with pytest.raises(HTTPException) as exc:
        routes_cell.cell_case_member_upsert(
            "dimy_docs",
            "dev1",
            routes_cell.UpdateCaseMemberRequest(role="viewer"),
            identity=routes_cell.CellIdentity(user_id="admin-not-owner"),
        )
    assert exc.value.status_code == 403


def test_member_upsert_persists_for_owner(monkeypatch):
    settings.cell_access_control_enabled = True
    monkeypatch.setattr(routes_cell, "_require_known_case", lambda _case_id: None)
    monkeypatch.setattr(routes_cell, "_actor_role", lambda *_args: "owner")
    monkeypatch.setattr(routes_cell, "global_owner_user_ids", lambda: set())

    captured = {}
    monkeypatch.setattr(
        routes_cell,
        "upsert_case_member",
        lambda case_id, user_id, role, assigned_by=None: captured.update(
            {"case_id": case_id, "user_id": user_id, "role": role, "assigned_by": assigned_by}
        ),
    )
    monkeypatch.setattr(
        routes_cell,
        "list_case_members",
        lambda _case_id: [CaseMember(case_id="dimy_docs", user_id="dev1", role="viewer", assigned_by="owner1")],
    )

    resp = routes_cell.cell_case_member_upsert(
        "dimy_docs",
        "dev1",
        routes_cell.UpdateCaseMemberRequest(role="viewer"),
        identity=routes_cell.CellIdentity(user_id="owner1"),
    )
    assert captured["case_id"] == "dimy_docs"
    assert captured["user_id"] == "dev1"
    assert resp.members[0].user_id == "dev1"


def test_markdown_link_extraction():
    links = routes_cell._extract_md_links("See [Guide](./guide.md) and [Site](https://example.com).")
    assert links == [("Guide", "./guide.md"), ("Site", "https://example.com")]


def test_cell_collective_summary_enforces_viewer_role(monkeypatch):
    settings.cell_access_control_enabled = True
    monkeypatch.setattr(routes_cell, "case_exists", lambda _case_id: True)
    monkeypatch.setattr(routes_cell, "has_case_role", lambda *_args: False)

    with pytest.raises(HTTPException) as exc:
        routes_cell.cell_collective_summary(
            "innovasjon_intervjuer",
            routes_cell.CellCollectiveSummaryRequest(
                questions=[InterviewQuestion(question_id="Q1", text="Hva er hovedtrekkene?")]
            ),
            identity=routes_cell.CellIdentity(user_id="u2"),
        )
    assert exc.value.status_code == 403


def test_cell_collective_summary_delegates_with_forced_case(monkeypatch):
    monkeypatch.setattr(routes_cell, "_require_role", lambda *_args: "viewer")
    monkeypatch.setattr(routes_cell, "validate_model_profile", lambda _profile: None)

    prepared = PreparedQuestionSet(
        question_set_id="set-1",
        source="inline",
        source_path=None,
        questions=[InterviewQuestion(question_id="Q1", text="Hva er hovedtrekkene?")],
    )
    monkeypatch.setattr(routes_cell, "prepare_question_set", lambda **_kwargs: prepared)

    captured = {}

    def _fake_build(**kwargs):
        captured.update(kwargs)
        return routes_cell.CollectiveSummaryResponse(
            case_id=kwargs["case_id"],
            question_set_id="set-1",
            question_count=1,
            succeeded_count=1,
            failed_count=0,
            items=[],
        )

    monkeypatch.setattr(routes_cell, "build_collective_summary", _fake_build)

    resp = routes_cell.cell_collective_summary(
        "innovasjon_intervjuer",
        routes_cell.CellCollectiveSummaryRequest(
            question_set_id="set-1",
            prompt_profile_case_id="innovasjon_bokskriving",
            questions=[InterviewQuestion(question_id="Q1", text="Hva er hovedtrekkene?")],
            top_k=8,
            model_profile="gpt-4o-mini",
        ),
        identity=routes_cell.CellIdentity(user_id="u1"),
    )
    assert captured["case_id"] == "innovasjon_intervjuer"
    assert captured["prompt_profile_case_id"] == "innovasjon_bokskriving"
    assert captured["top_k"] == 8
    assert resp.question_set_id == "set-1"
