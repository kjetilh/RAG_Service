from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from app.api.routes_chat import router as chat_router
from app.api.routes_ui import router as ui_router
from app.api.routes_admin import router as admin_router
from app.api.routes_cell import router as cell_router
from app.api.routes_interviews import router as interviews_router
from app.api.routes_research import router as research_router
from app.rag.generate.llm_provider import llm_unavailable_reason
from app.settings import settings

app = FastAPI(title="Innovation RAG Service", version="0.1.0")


# Serve static assets
app.mount("/static", StaticFiles(directory="app/static"), name="static")
app.include_router(ui_router)
app.include_router(chat_router)
app.include_router(admin_router)
app.include_router(cell_router)
app.include_router(interviews_router)
app.include_router(research_router)

@app.get("/health")
def health():
    return {"ok": True}


# --- Warm-up and a readable account of how retrieval is configured -------------
# The first question after a restart used to pay for loading the embedding model,
# the BM25 index and the cross-encoder (11 s measured 2026-10-08). With
# WARM_UP_ON_START=true that happens in the background at start-up instead.
_warm: dict = {"requested": False, "embedder": False, "bm25": False, "reranker": False, "error": None,
               "started_at": None, "finished_at": None}


def _warm_up() -> None:
    import time as _time
    _warm["started_at"] = _time.time()
    try:
        from app.rag.index.embedder import default_embedder
        default_embedder().embed_query("warm up")
        _warm["embedder"] = True
        if str(settings.lexical_mode).lower() == "bm25":
            from app.rag.index.bm25_store import get_index
            get_index()
            _warm["bm25"] = True
        if bool(settings.reranker_enabled):
            from app.rag.retrieve.hybrid import RetrievedChunk
            from app.rag.retrieve.rerank import default_reranker
            default_reranker().rerank("warm up", [RetrievedChunk("c", "d", 0, "t", None, None, None, None, None, None, None, "warm up", 0.0, "vector")])
            _warm["reranker"] = True
    except Exception as exc:  # never fatal: the first request simply loads what is missing
        _warm["error"] = repr(exc)[:300]
    _warm["finished_at"] = _time.time()


@app.on_event("startup")
def _start_warm_up() -> None:
    if bool(getattr(settings, "warm_up_on_start", False)):
        import threading
        _warm["requested"] = True
        threading.Thread(target=_warm_up, name="warm-up", daemon=True).start()


@app.get("/v1/retrieval/config")
def retrieval_config():
    """Non-secret retrieval settings of this instance, so "what is switched on"
    can be read from the running service instead of from a config file."""
    return {
        "embedding_model": settings.embedding_model,
        "chunker_version": settings.chunker_version,
        "doc_id_scheme": settings.doc_id_scheme,
        "hybrid_fusion": settings.hybrid_fusion,
        "lexical_mode": settings.lexical_mode,
        "vector_exact_search": bool(settings.vector_exact_search),
        "graph_mode": settings.graph_mode,
        "reranker_enabled": bool(settings.reranker_enabled),
        "reranker_model": settings.reranker_model if settings.reranker_enabled else None,
        "reranker_top_n": int(settings.reranker_top_n),
        "top_k_vector": int(settings.top_k_vector),
        "top_k_lexical": int(settings.top_k_lexical),
        "top_k_final": int(settings.top_k_final),
        "max_chunks_per_doc": int(settings.max_chunks_per_doc),
        "llm_unavailable_reason": llm_unavailable_reason(),
        "warm_up": dict(_warm),
    }
