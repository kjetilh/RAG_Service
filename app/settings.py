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
    query_router_enabled: bool = False
    query_router_docs_source_types_json: str = ""
    query_router_prompts_source_types_json: str = ""
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


settings = Settings()
