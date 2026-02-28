from app.rag.audit.coverage_report import build_coverage_actions
from app.settings import settings


_ROUTER_KEYS = [
    "query_router_enabled",
    "query_router_docs_source_types_json",
    "query_router_prompts_source_types_json",
    "query_router_docs_keywords_json",
    "query_router_prompts_keywords_json",
]


def _set_router_defaults():
    settings.query_router_enabled = True
    settings.query_router_docs_source_types_json = '["haven_docs","cellprotocol_docs"]'
    settings.query_router_prompts_source_types_json = '["dimy_prompts","prompt_docs"]'
    settings.query_router_docs_keywords_json = '["api","kode"]'
    settings.query_router_prompts_keywords_json = '["prompt","template"]'


def test_build_coverage_actions_generates_prioritized_actions():
    original = {k: getattr(settings, k) for k in _ROUTER_KEYS}
    try:
        _set_router_defaults()
        report = {
            "summary": {"total_documents": 10, "total_chunks": 100},
            "domain_counts": {"docs": 7, "prompts": 2, "unclassified": 1},
            "by_source_type": {
                "haven_docs": {"documents": 4, "chunks": 40},
                "dimy_prompts": {"documents": 2, "chunks": 20},
                "legacy_docs": {"documents": 1, "chunks": 5},
            },
            "metadata_coverage": {
                "missing_author": 1,
                "missing_year": 1,
                "missing_url": 2,
                "missing_language": 0,
                "missing_file_path": 1,
            },
            "gaps": {
                "missing_files_count": 2,
                "missing_files_sample": [{"source_type": "haven_docs"}],
                "thin_documents_count": 3,
                "thin_documents_sample": [{"doc_id": "x"}],
                "duplicate_titles": [{"normalized_title": "abc", "duplicates": 2}],
            },
        }
        actions_payload = build_coverage_actions(report)
        ids = [a["id"] for a in actions_payload["actions"]]

        assert actions_payload["summary"]["total_documents"] == 10
        assert "fix_missing_files" in ids
        assert "classify_source_types" in ids
        assert "router_tuning" in ids
    finally:
        for k, v in original.items():
            setattr(settings, k, v)
