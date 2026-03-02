from pathlib import Path

from scripts import sync_orchestrator as orchestrator


def test_load_config_parses_basic_toml(tmp_path: Path):
    cfg_path = tmp_path / "sync_orchestrator.toml"
    cfg_path.write_text(
        """
[orchestrator]
ingest_root = "/tmp/rag/uploads"
ingest_live_subdir = "cell_haven_docs_live"
admin_base_url = "http://127.0.0.1:8102"
admin_api_key_env = "RAG_DIMY_ADMIN_API_KEY"

[[source]]
name = "CellProtocol"
repo_path = "/tmp/repos/CellProtocol"
source_type = "cellprotocol_docs"
target_subdir = "cellprotocol/CellProtocol"
""",
        encoding="utf-8",
    )

    cfg = orchestrator.load_config(cfg_path)
    assert cfg.settings.admin_base_url == "http://127.0.0.1:8102"
    assert cfg.settings.ingest_live_subdir == "cell_haven_docs_live"
    assert len(cfg.sources) == 1
    assert cfg.sources[0].name == "CellProtocol"
    assert cfg.sources[0].source_type == "cellprotocol_docs"


def test_mirror_source_files_create_update_delete(tmp_path: Path):
    src_root = tmp_path / "src"
    src_root.mkdir(parents=True)
    (src_root / "a.md").write_text("A1", encoding="utf-8")
    (src_root / "nested").mkdir()
    (src_root / "nested" / "b.md").write_text("B1", encoding="utf-8")

    target_root = tmp_path / "target"
    (target_root / "nested").mkdir(parents=True)
    (target_root / "a.md").write_text("OLD", encoding="utf-8")
    (target_root / "nested" / "old.md").write_text("remove", encoding="utf-8")

    source_files = {
        "a.md": src_root / "a.md",
        "nested/b.md": src_root / "nested" / "b.md",
    }
    summary = orchestrator.mirror_source_files(source_files, target_root, plan_only=False)

    assert summary["created_files"] == 1
    assert summary["updated_files"] == 1
    assert summary["deleted_files"] == 1
    assert summary["unchanged_files"] == 0
    assert (target_root / "nested" / "b.md").is_file()
    assert not (target_root / "nested" / "old.md").exists()


def test_run_orchestrator_with_skip_sync(tmp_path: Path):
    repo_root = tmp_path / "repo"
    repo_root.mkdir(parents=True)
    (repo_root / "README.md").write_text("hello", encoding="utf-8")
    (repo_root / "ignore.log").write_text("nope", encoding="utf-8")

    cfg = orchestrator.OrchestratorConfig(
        settings=orchestrator.OrchestratorSettings(
            ingest_root=tmp_path / "uploads",
            ingest_live_subdir="cell_haven_docs_live",
            admin_base_url="http://127.0.0.1:8102",
            admin_api_key_env="RAG_DIMY_ADMIN_API_KEY",
            request_timeout_sec=30,
            include_default=["**/*.md"],
            exclude_default=[],
            fetch_coverage_actions=False,
        ),
        sources=[
            orchestrator.SourceSpec(
                name="RepoDocs",
                repo_path=repo_root,
                source_type="haven_docs",
                target_subdir="repo/docs",
                include=["**/*.md"],
                exclude=[],
            )
        ],
    )

    result = orchestrator.run_orchestrator(cfg, skip_sync=True)
    assert result["ok"] is True
    assert result["source_count"] == 1
    source = result["sources"][0]
    assert source["export"]["scanned_files"] == 1
    assert source["sync"]["skipped"] is True
    assert source["sync"]["reason"] == "skip_sync"
    mirrored = tmp_path / "uploads" / "cell_haven_docs_live" / "repo" / "docs" / "README.md"
    assert mirrored.is_file()


def test_trigger_admin_sync_builds_expected_payload(monkeypatch):
    captured = {}

    def fake_http_json_request(*, method, url, timeout_sec, headers, payload):
        captured["method"] = method
        captured["url"] = url
        captured["headers"] = headers
        captured["payload"] = payload
        captured["timeout_sec"] = timeout_sec
        return 200, {"ok": True, "summary": {"created_docs": 1}}

    monkeypatch.setenv("RAG_DIMY_ADMIN_API_KEY", "secret")
    monkeypatch.setattr(orchestrator, "_http_json_request", fake_http_json_request)

    settings = orchestrator.OrchestratorSettings(
        ingest_root=Path("/tmp/uploads"),
        ingest_live_subdir="cell_haven_docs_live",
        admin_base_url="http://127.0.0.1:8102",
        admin_api_key_env="RAG_DIMY_ADMIN_API_KEY",
        request_timeout_sec=42,
        include_default=[],
        exclude_default=[],
        fetch_coverage_actions=True,
    )
    source = orchestrator.SourceSpec(
        name="CellProtocol",
        repo_path=Path("/tmp/repo"),
        source_type="cellprotocol_docs",
        target_subdir="cellprotocol",
        include=["**/*.md"],
        exclude=[],
        author="team",
        year=2026,
        delete_missing=True,
    )

    res = orchestrator.trigger_admin_sync(
        settings=settings,
        source=source,
        sync_rel_path="cell_haven_docs_live/cellprotocol",
        sync_dry_run=True,
    )
    assert res["ok"] is True
    assert captured["method"] == "POST"
    assert captured["url"] == "http://127.0.0.1:8102/v1/admin/sync"
    assert captured["headers"]["X-API-Key"] == "secret"
    assert captured["timeout_sec"] == 42
    assert captured["payload"]["path"] == "cell_haven_docs_live/cellprotocol"
    assert captured["payload"]["source_type"] == "cellprotocol_docs"
    assert captured["payload"]["dry_run"] is True
