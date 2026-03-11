import numpy as np

from app.rag.index import lexical_store, vector_store


class _FakeConn:
    def __init__(self):
        self.calls = []

    def execute(self, statement, params):
        self.calls.append((str(statement), params))
        return self

    def fetchall(self):
        return []


class _FakeBegin:
    def __init__(self, conn):
        self.conn = conn

    def __enter__(self):
        return self.conn

    def __exit__(self, exc_type, exc, tb):
        return False


class _FakeEngine:
    def __init__(self, conn):
        self.conn = conn

    def begin(self):
        return _FakeBegin(self.conn)


def test_lexical_search_filters_out_non_active_docs(monkeypatch):
    conn = _FakeConn()
    monkeypatch.setattr(lexical_store, "engine", lambda: _FakeEngine(conn))

    lexical_store.lexical_search("api", top_k=5, filters={"source_type": ["haven_docs"]})

    sql, params = conn.calls[0]
    assert "COALESCE(d.doc_state, 'active') = 'active'" in sql
    assert params["source_type"] == ["haven_docs"]


def test_vector_search_filters_out_non_active_docs(monkeypatch):
    conn = _FakeConn()
    monkeypatch.setattr(vector_store, "engine", lambda: _FakeEngine(conn))

    vector_store.vector_search(np.array([0.1, 0.2], dtype=float), top_k=5, filters={"doc_id": ["d1"]})

    sql, params = conn.calls[0]
    assert "COALESCE(d.doc_state, 'active') = 'active'" in sql
    assert params["doc_id"] == ["d1"]
