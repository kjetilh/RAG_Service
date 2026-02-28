from pathlib import Path

from app.rag.audit.coverage_report import analyze_coverage


def test_analyze_coverage_reports_missing_files_and_thin_docs(tmp_path: Path):
    live = tmp_path / "live"
    live.mkdir(parents=True)
    existing = live / "exists.md"
    existing.write_text("hello", encoding="utf-8")

    rows = [
        {
            "doc_id": "d1",
            "title": "Doc 1",
            "source_type": "haven_docs",
            "author": None,
            "year": None,
            "url": None,
            "language": None,
            "file_path": str(existing),
        },
        {
            "doc_id": "d2",
            "title": "Doc 2",
            "source_type": "dimy_prompts",
            "author": "A",
            "year": 2025,
            "url": None,
            "language": "no",
            "file_path": str(live / "missing.md"),
        },
    ]
    chunk_map = {"d1": 1, "d2": 3}

    report = analyze_coverage(
        doc_rows=rows,
        chunk_count_by_doc=chunk_map,
        duplicate_title_rows=[],
        ingest_root=str(tmp_path),
        docs_source_types=["haven_docs"],
        prompts_source_types=["dimy_prompts"],
    )

    assert report["summary"]["total_documents"] == 2
    assert report["summary"]["total_chunks"] == 4
    assert report["domain_counts"]["docs"] == 1
    assert report["domain_counts"]["prompts"] == 1
    assert report["gaps"]["missing_files_count"] == 1
    assert report["gaps"]["thin_documents_count"] == 1
    assert report["metadata_coverage"]["missing_author"] == 1
