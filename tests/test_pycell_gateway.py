import asyncio
import importlib.util

import pytest

from app.models.schemas import Citation, QueryResponse, RetrieveResponse
from app.rag import pycell_gateway


def run(coro):
    return asyncio.run(coro)


def test_pycell_backend_retrieve_uses_inprocess_route(monkeypatch):
    captured = {}

    def _fake_run_retrieve(req):
        captured["request"] = req
        return RetrieveResponse(
            context_text="context",
            citations=[Citation(doc_id="d1", title="Doc", chunk_id="c1", score=0.8, excerpt="x")],
            retrieval_debug={"query_plan": {"selected_case": "dimy_docs"}},
            trace={"selected_case": "dimy_docs"},
        )

    monkeypatch.setattr(pycell_gateway.routes_chat, "_run_retrieve", _fake_run_retrieve)

    resp = pycell_gateway.RAGGatewayBackend().retrieve(
        {"query": "hei", "case_id": "dimy_docs", "top_k": 4, "rewrite_query": False}
    )

    assert captured["request"].case_id == "dimy_docs"
    assert captured["request"].top_k == 4
    assert captured["request"].rewrite_query is False
    assert resp["context_text"] == "context"
    assert resp["citations"][0]["doc_id"] == "d1"


def test_pycell_backend_query_returns_trace(monkeypatch):
    def _fake_run_query(req):
        assert req.case_id == "dimy_docs"
        return QueryResponse(
            answer="ok",
            citations=[Citation(doc_id="d1", title="Doc", chunk_id="c1", score=0.8, excerpt="x")],
            retrieval_debug={"query_plan": {"selected_case": "dimy_docs"}},
        )

    monkeypatch.setattr(pycell_gateway.routes_chat, "_run_query", _fake_run_query)

    resp = pycell_gateway.RAGGatewayBackend().query({"query": "hei", "case_id": "dimy_docs"})

    assert resp["answer"] == "ok"
    assert resp["trace"] == {"selected_case": "dimy_docs"}


def test_pycell_gateway_cell_is_optional_when_pycellprotocol_missing():
    if importlib.util.find_spec("cellprotocol") is not None:
        pytest.skip("PyCellProtocol is importable in this environment")

    with pytest.raises(pycell_gateway.PyCellProtocolUnavailable):
        pycell_gateway.create_rag_gateway_cell()


def test_pycell_gateway_cell_contract_when_dependency_available(monkeypatch):
    pytest.importorskip("cellprotocol")

    backend = pycell_gateway.RAGGatewayBackend()
    monkeypatch.setattr(backend, "list_cases", lambda: {"cases": [{"case_id": "dimy_docs"}]})
    monkeypatch.setattr(
        backend,
        "retrieve",
        lambda payload: {"context_text": payload["query"], "citations": [], "retrieval_debug": {}, "trace": {}},
    )

    cell = pycell_gateway.create_rag_gateway_cell(backend=backend)

    assert run(cell.get("cases.list")) == {"cases": [{"case_id": "dimy_docs"}]}
    assert run(cell.set("retrieve.run", {"query": "hello", "case_id": "dimy_docs"}))["context_text"] == "hello"
    assert "retrieve.run" in run(cell.keys())
