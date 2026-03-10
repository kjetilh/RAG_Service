from app.api import routes_chat
from app.models.schemas import (
    ChatRequest,
    ChatResponse,
    Citation,
    QueryRequest,
)


def _resp_with_plan():
    return ChatResponse(
        answer="ok",
        citations=[
            Citation(
                doc_id="d1",
                title="T",
                chunk_id="c1",
                score=0.9,
                excerpt="x",
            )
        ],
        retrieval_debug={"query_plan": {"planner_mode": "deterministic", "selected_case": "docs_case"}},
    )


def test_query_endpoint_passes_case_id_in_filters(monkeypatch):
    captured = {}
    monkeypatch.setattr(routes_chat, "validate_model_profile", lambda _: None)
    monkeypatch.setattr(
        routes_chat,
        "load_rag_cases",
        lambda _path: type("Cfg", (), {"cases": [], "default_case": "innovasjon"})(),
    )
    monkeypatch.setattr(routes_chat, "case_by_id", lambda _cfg, case_id: type("Case", (), {"case_id": case_id})())

    def fake_answer_question(**kwargs):
        captured.update(kwargs)
        return _resp_with_plan()

    monkeypatch.setattr(routes_chat, "answer_question", fake_answer_question)

    resp = routes_chat.query(
        QueryRequest(
            query="hei",
            case_id="innovasjon",
            prompt_profile_case_id="innovasjon_intervjuer",
            filters={"source_type": ["haven_docs"]},
            top_k=7,
        )
    )

    assert captured["message"] == "hei"
    assert captured["top_k"] == 7
    assert captured["filters"]["source_type"] == ["haven_docs"]
    assert captured["filters"]["rag_case_id"] == "innovasjon"
    assert captured["prompt_profile_case_id"] == "innovasjon_intervjuer"
    assert resp.trace["selected_case"] == "docs_case"


def test_chat_endpoint_is_backward_compatible_shim(monkeypatch):
    captured = {}

    def _fake_run_query(req):
        captured["case_id"] = req.case_id
        return _resp_with_plan()

    monkeypatch.setattr(routes_chat, "_run_query", _fake_run_query)

    resp = routes_chat.chat(ChatRequest(message="hei", case_id="innovasjon_bokskriving"))
    assert resp.answer == "ok"
    assert captured["case_id"] == "innovasjon_bokskriving"
    assert resp.retrieval_debug["query_plan"]["planner_mode"] == "deterministic"


def test_list_cases_only_returns_enabled_cases(monkeypatch):
    cfg = type(
        "Cfg",
        (),
        {
            "cases": [
                type(
                    "Case",
                    (),
                    {
                        "case_id": "innovasjon",
                        "description": "A",
                        "enabled": True,
                        "planner": type("Planner", (), {"docs_source_types": ["innovasjonsledelse"], "prompts_source_types": []})(),
                    },
                )(),
                type(
                    "Case",
                    (),
                    {
                        "case_id": "disabled",
                        "description": "B",
                        "enabled": False,
                        "planner": type("Planner", (), {"docs_source_types": ["disabled_type"], "prompts_source_types": []})(),
                    },
                )(),
            ]
        },
    )()
    monkeypatch.setattr(routes_chat, "load_rag_cases", lambda _path: cfg)
    monkeypatch.setattr(routes_chat, "_available_source_types", lambda: {"innovasjonsledelse"})

    resp = routes_chat.list_cases()

    assert resp == {"cases": [{"case_id": "innovasjon", "description": "A", "enabled": True}]}
