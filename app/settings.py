from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "postgresql+psycopg://rag:rag@localhost:5432/ragdb"
    app_env: str = "dev"
    log_level: str = "INFO"

    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"

    llm_provider: str = "openai_compat"
    llm_base_url: str = "https://api.openai.com/v1"
    llm_api_key: str = ""
    llm_model: str = "gpt-4o-mini"
    llm_profiles_json: str = ""
    system_persona_path: str = ""
    answer_template_path: str = ""
    next_gen_rag_enabled: bool = False
    rag_cases_path: str = "config/rag_cases.yml"
    instance_case_ids_json: str = ""
    cell_access_control_enabled: bool = False
    cell_gateway_shared_secret: str = ""
    cell_owner_user_ids_json: str = "[]"
    research_api_tokens_json: str = ""
    research_download_signing_key: str = ""
    research_download_ttl_seconds: int = 300
    query_router_enabled: bool = False
    query_router_docs_source_types_json: str = ""
    query_router_prompts_source_types_json: str = ""
    query_router_docs_keywords_json: str = ""
    query_router_prompts_keywords_json: str = ""

    top_k_vector: int = 50
    top_k_lexical: int = 50
    top_k_final: int = 12
    max_chunks_per_doc: int = 3

    # NEW: query rewrite
    query_rewrite_enabled: bool = True

    # NEW: reranking
    reranker_enabled: bool = False
    reranker_model: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"

    # NEW: grounding
    grounding_min_citations: int = 2

    # NEW: streaming
    stream_chunk_chars: int = 80

    # Admin endpoint protection
    admin_api_key: str = ""

    # Restrict admin ingest to this filesystem root
    ingest_root: str = "/data/uploads"
    sync_tombstone_enabled: bool = False
    sync_tombstone_grace_seconds: int = 900
    sync_anti_thrash_batch_size: int = 200

    # --- Retrieval quality (2026-10-08). Defaults keep the previous behaviour;
    # the documentation RAG turns these on through its environment. Every value
    # here was measured with scripts/eval_retrieval.py before it was enabled.
    # v1: split on headings, body only. v2: heading-path aware, small sections
    # merged, document title + heading path indexed with the body.
    chunker_version: str = "v1"
    # v1: "<stem>-<hash(content)>" (two files with the same name and content
    # collide and make sync flip-flop). v2 includes the file path.
    doc_id_scheme: str = "v1"
    # max: best raw score per chunk (lexical scores never win over cosine).
    # rrf: reciprocal rank fusion of the vector and lexical rankings.
    hybrid_fusion: str = "max"
    rrf_k: int = 60
    # and: plainto_tsquery (every query word must be in the chunk).
    # bm25: in-process BM25 over the indexed chunk text, OR semantics.
    lexical_mode: str = "and"
    # E5-style models need "query: " / "passage: " prefixes.
    embedding_query_prefix: str = ""
    embedding_passage_prefix: str = ""
    # ivfflat with the default probes=1 scans about 1 % of the vectors; for
    # corpora of this size an exact scan is both fast and correct.
    vector_exact_search: bool = True
    # off | expand: the best chunk of documents linked from the top documents
    # takes the last graph_add places of the context (reserved slots); the
    # ranking above them is not changed. See app/rag/retrieve/graph_expand.py.
    graph_mode: str = "off"
    graph_head: int = 4
    graph_fan: int = 4
    graph_add: int = 2
    reranker_top_n: int = 30
    reranker_max_length: int = 384


settings = Settings()
