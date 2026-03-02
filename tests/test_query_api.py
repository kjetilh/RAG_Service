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

    def fake_answer_question(**kwargs):
        captured.update(kwargs)
        return _resp_with_plan()

    monkeypatch.setattr(routes_chat, "answer_question", fake_answer_question)

    resp = routes_chat.query(
        QueryRequest(
            query="hei",
            case_id="innovasjon",
            filters={"source_type": ["haven_docs"]},
            top_k=7,
        )
    )

    assert captured["message"] == "hei"
    assert captured["top_k"] == 7
    assert captured["filters"]["source_type"] == ["haven_docs"]
    assert captured["filters"]["rag_case_id"] == "innovasjon"
    assert resp.trace["selected_case"] == "docs_case"


def test_chat_endpoint_is_backward_compatible_shim(monkeypatch):
    monkeypatch.setattr(routes_chat, "_run_query", lambda req: _resp_with_plan())

    resp = routes_chat.chat(ChatRequest(message="hei"))
    assert resp.answer == "ok"
    assert resp.retrieval_debug["query_plan"]["planner_mode"] == "deterministic"
