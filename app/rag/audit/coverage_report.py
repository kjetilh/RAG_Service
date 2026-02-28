from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping

from sqlalchemy import text

from app.rag.index.db import engine
from app.rag.retrieve.query_router import router_config_from_settings
from app.settings import settings


def _is_within(path: Path, root: Path) -> bool:
    return path == root or root in path.parents


def resolve_existing_file(stored_file_path: str, ingest_root: str | None = None) -> Path | None:
    root_value = ingest_root or settings.ingest_root
    root = Path(root_value).expanduser().resolve(strict=False)
    requested = Path(stored_file_path).expanduser()
    candidate = requested.resolve(strict=False) if requested.is_absolute() else (root / requested).resolve(strict=False)
    if not _is_within(candidate, root):
        return None
    if candidate.is_file():
        return candidate

    try:
        rel = candidate.relative_to(root)
    except Exception:
        return None

    done_candidate = (root / "done" / rel).resolve(strict=False)
    if _is_within(done_candidate, root) and done_candidate.is_file():
        return done_candidate
    failed_candidate = (root / "failed" / rel).resolve(strict=False)
    if _is_within(failed_candidate, root) and failed_candidate.is_file():
        return failed_candidate
    return None


def _normalize_source_type(value: Any) -> str:
    if value is None:
        return "<null>"
    text_value = str(value).strip()
    return text_value if text_value else "<empty>"


def analyze_coverage(
    *,
    doc_rows: Iterable[Mapping[str, Any]],
    chunk_count_by_doc: Dict[str, int],
    duplicate_title_rows: Iterable[Mapping[str, Any]],
    ingest_root: str | None = None,
    docs_source_types: Iterable[str] | None = None,
    prompts_source_types: Iterable[str] | None = None,
) -> Dict[str, Any]:
    rows = list(doc_rows)
    docs_types = set(docs_source_types or [])
    prompts_types = set(prompts_source_types or [])

    total_docs = len(rows)
    total_chunks = 0
    by_source_type: Dict[str, Dict[str, Any]] = defaultdict(lambda: {"documents": 0, "chunks": 0})

    missing_author = 0
    missing_year = 0
    missing_url = 0
    missing_language = 0
    missing_file_path = 0

    missing_files: list[Dict[str, Any]] = []
    thin_docs: list[Dict[str, Any]] = []
    domain_counts = {"docs": 0, "prompts": 0, "unclassified": 0}

    for row in rows:
        doc_id = str(row.get("doc_id") or "")
        source_type = _normalize_source_type(row.get("source_type"))
        chunks = int(chunk_count_by_doc.get(doc_id, 0))
        total_chunks += chunks
        by_source_type[source_type]["documents"] += 1
        by_source_type[source_type]["chunks"] += chunks

        if not row.get("author"):
            missing_author += 1
        if row.get("year") is None:
            missing_year += 1
        if not row.get("url"):
            missing_url += 1
        if not row.get("language"):
            missing_language += 1
        if not row.get("file_path"):
            missing_file_path += 1

        if source_type in docs_types:
            domain_counts["docs"] += 1
        elif source_type in prompts_types:
            domain_counts["prompts"] += 1
        else:
            domain_counts["unclassified"] += 1

        if chunks <= 1:
            thin_docs.append(
                {
                    "doc_id": doc_id,
                    "title": row.get("title"),
                    "source_type": source_type,
                    "chunk_count": chunks,
                }
            )

        file_path = row.get("file_path")
        if file_path and resolve_existing_file(str(file_path), ingest_root=ingest_root) is None:
            missing_files.append(
                {
                    "doc_id": doc_id,
                    "title": row.get("title"),
                    "source_type": source_type,
                    "file_path": str(file_path),
                }
            )

    recommendations: list[str] = []
    if total_docs == 0:
        recommendations.append("Ingen dokumenter indeksert. Start med ingest eller sync.")
    if missing_files:
        recommendations.append("Noen dokumenter peker til filer som ikke finnes. Kjør sync og verifiser kildemappar.")
    if thin_docs:
        recommendations.append("Flere dokumenter har få chunks. Vurder bedre struktur eller rikere kilder.")
    if domain_counts["prompts"] == 0:
        recommendations.append("Ingen prompt-kilder funnet. Vurder egen source_type for promptdokumentasjon.")
    if domain_counts["unclassified"] > 0:
        recommendations.append("Noen kilder er uklassifisert. Standardiser source_type for bedre routing.")

    metadata_coverage = {
        "missing_author": missing_author,
        "missing_year": missing_year,
        "missing_url": missing_url,
        "missing_language": missing_language,
        "missing_file_path": missing_file_path,
    }

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "total_documents": total_docs,
            "total_chunks": total_chunks,
            "average_chunks_per_document": round((total_chunks / total_docs), 2) if total_docs else 0.0,
        },
        "domain_counts": domain_counts,
        "by_source_type": dict(sorted(by_source_type.items(), key=lambda kv: kv[0])),
        "metadata_coverage": metadata_coverage,
        "gaps": {
            "missing_files_count": len(missing_files),
            "missing_files_sample": missing_files[:25],
            "thin_documents_count": len(thin_docs),
            "thin_documents_sample": thin_docs[:25],
            "duplicate_titles": list(duplicate_title_rows),
        },
        "recommendations": recommendations,
    }


def build_coverage_report() -> Dict[str, Any]:
    cfg = router_config_from_settings()

    with engine().begin() as conn:
        doc_rows = conn.execute(
            text(
                """
                SELECT doc_id, title, source_type, author, year, url, language, file_path, created_at
                FROM documents
                ORDER BY created_at DESC
                """
            )
        ).mappings().all()

        chunk_rows = conn.execute(
            text(
                """
                SELECT doc_id, COUNT(*) AS chunk_count
                FROM chunks
                GROUP BY doc_id
                """
            )
        ).mappings().all()

        duplicate_rows = conn.execute(
            text(
                """
                SELECT LOWER(title) AS normalized_title, COUNT(*) AS duplicates, ARRAY_AGG(doc_id) AS doc_ids
                FROM documents
                WHERE title IS NOT NULL AND BTRIM(title) <> ''
                GROUP BY LOWER(title)
                HAVING COUNT(*) > 1
                ORDER BY duplicates DESC
                LIMIT 25
                """
            )
        ).mappings().all()

    chunk_map = {str(r["doc_id"]): int(r["chunk_count"]) for r in chunk_rows}
    return analyze_coverage(
        doc_rows=doc_rows,
        chunk_count_by_doc=chunk_map,
        duplicate_title_rows=duplicate_rows,
        ingest_root=settings.ingest_root,
        docs_source_types=cfg.docs_source_types,
        prompts_source_types=cfg.prompts_source_types,
    )
