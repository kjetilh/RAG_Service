from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
import shutil
import tomllib
from typing import Any, Iterable
import urllib.error
import urllib.request


DEFAULT_INCLUDE_GLOBS = ["**/*.md", "**/*.markdown", "**/*.txt", "**/*.html", "**/*.htm", "**/*.pdf", "**/*.docx"]
DEFAULT_EXCLUDE_GLOBS = [
    "**/.git/**",
    "**/.venv/**",
    "**/node_modules/**",
    "**/__pycache__/**",
    "**/.build/**",
    "**/.swiftpm/**",
]


@dataclass
class SourceSpec:
    name: str
    repo_path: Path
    source_type: str
    target_subdir: str
    include: list[str]
    exclude: list[str]
    author: str | None = None
    year: int | None = None
    delete_missing: bool = True


@dataclass
class OrchestratorSettings:
    ingest_root: Path
    ingest_live_subdir: str
    admin_base_url: str
    admin_api_key_env: str
    request_timeout_sec: int
    include_default: list[str]
    exclude_default: list[str]
    fetch_coverage_actions: bool


@dataclass
class OrchestratorConfig:
    settings: OrchestratorSettings
    sources: list[SourceSpec]


def _string_list(value: Any, default: Iterable[str]) -> list[str]:
    if value is None:
        return list(default)
    if not isinstance(value, list):
        raise ValueError("Expected a list of strings.")
    out: list[str] = []
    for item in value:
        if not isinstance(item, str):
            continue
        s = item.strip()
        if s:
            out.append(s)
    return out if out else list(default)


def _normalize_rel_posix(value: str, *, field_name: str, allow_empty: bool = False) -> str:
    raw = (value or "").strip().replace("\\", "/")
    if not raw:
        if allow_empty:
            return ""
        raise ValueError(f"{field_name} cannot be empty")

    p = PurePosixPath(raw)
    if p.is_absolute():
        raise ValueError(f"{field_name} must be relative, got absolute path: {value}")
    if any(part == ".." for part in p.parts):
        raise ValueError(f"{field_name} cannot contain '..': {value}")

    normalized = "" if str(p) == "." else str(p)
    if not normalized and not allow_empty:
        raise ValueError(f"{field_name} cannot resolve to empty path")
    return normalized


def _join_rel_posix(*parts: str) -> str:
    cleaned = [_normalize_rel_posix(p, field_name="path-part", allow_empty=True) for p in parts]
    cleaned = [p for p in cleaned if p]
    return "/".join(cleaned)


def load_config(config_path: str | Path) -> OrchestratorConfig:
    path = Path(config_path).expanduser().resolve(strict=False)
    if not path.is_file():
        raise FileNotFoundError(f"Config file not found: {path}")

    with path.open("rb") as f:
        raw = tomllib.load(f)

    orch_raw = raw.get("orchestrator")
    if not isinstance(orch_raw, dict):
        raise ValueError("Missing [orchestrator] section in config.")

    ingest_root = Path(str(orch_raw.get("ingest_root", "")).strip()).expanduser().resolve(strict=False)
    if str(ingest_root) == ".":
        raise ValueError("orchestrator.ingest_root is required")

    admin_base_url = str(orch_raw.get("admin_base_url", "")).strip().rstrip("/")
    if not admin_base_url:
        raise ValueError("orchestrator.admin_base_url is required")

    settings = OrchestratorSettings(
        ingest_root=ingest_root,
        ingest_live_subdir=_normalize_rel_posix(
            str(orch_raw.get("ingest_live_subdir", "cell_haven_docs_live")),
            field_name="orchestrator.ingest_live_subdir",
            allow_empty=True,
        ),
        admin_base_url=admin_base_url,
        admin_api_key_env=str(orch_raw.get("admin_api_key_env", "RAG_DIMY_ADMIN_API_KEY")).strip()
        or "RAG_DIMY_ADMIN_API_KEY",
        request_timeout_sec=int(orch_raw.get("request_timeout_sec", 120)),
        include_default=_string_list(orch_raw.get("include_default"), DEFAULT_INCLUDE_GLOBS),
        exclude_default=_string_list(orch_raw.get("exclude_default"), DEFAULT_EXCLUDE_GLOBS),
        fetch_coverage_actions=bool(orch_raw.get("fetch_coverage_actions", True)),
    )

    sources_raw = raw.get("source")
    if not isinstance(sources_raw, list) or not sources_raw:
        raise ValueError("Config must include at least one [[source]] block.")

    sources: list[SourceSpec] = []
    names: set[str] = set()
    for idx, src_raw in enumerate(sources_raw):
        if not isinstance(src_raw, dict):
            raise ValueError(f"source[{idx}] must be a table")

        name = str(src_raw.get("name", "")).strip()
        if not name:
            raise ValueError(f"source[{idx}] missing name")
        if name in names:
            raise ValueError(f"Duplicate source name: {name}")
        names.add(name)

        repo_path_value = str(src_raw.get("repo_path", "")).strip()
        if not repo_path_value:
            raise ValueError(f"source[{idx}] missing repo_path")
        repo_subpath = str(src_raw.get("repo_subpath", "")).strip()
        repo_root = Path(repo_path_value).expanduser().resolve(strict=False)
        repo_path = (repo_root / repo_subpath).resolve(strict=False) if repo_subpath else repo_root

        source_type = str(src_raw.get("source_type", "")).strip()
        if not source_type:
            raise ValueError(f"source[{idx}] missing source_type")

        target_subdir = _normalize_rel_posix(
            str(src_raw.get("target_subdir", name)),
            field_name=f"source[{idx}].target_subdir",
        )
        include = _string_list(src_raw.get("include"), settings.include_default)
        exclude = settings.exclude_default + _string_list(src_raw.get("exclude"), [])

        year_raw = src_raw.get("year")
        year = int(year_raw) if year_raw is not None else None

        sources.append(
            SourceSpec(
                name=name,
                repo_path=repo_path,
                source_type=source_type,
                target_subdir=target_subdir,
                include=include,
                exclude=exclude,
                author=(str(src_raw.get("author")).strip() if src_raw.get("author") is not None else None),
                year=year,
                delete_missing=bool(src_raw.get("delete_missing", True)),
            )
        )

    return OrchestratorConfig(settings=settings, sources=sources)


def _matches_any(path_posix: str, patterns: list[str]) -> bool:
    return any(fnmatch.fnmatch(path_posix, pattern) for pattern in patterns)


def collect_source_files(source: SourceSpec) -> dict[str, Path]:
    root = source.repo_path.resolve(strict=False)
    if not root.exists():
        raise FileNotFoundError(f"[{source.name}] repo_path not found: {root}")
    if not root.is_dir():
        raise NotADirectoryError(f"[{source.name}] repo_path is not a directory: {root}")

    files: dict[str, Path] = {}
    for pattern in source.include:
        for candidate in root.glob(pattern):
            if not candidate.is_file():
                continue
            rel = candidate.relative_to(root).as_posix()
            if _matches_any(rel, source.exclude):
                continue
            files[rel] = candidate.resolve(strict=False)
    return dict(sorted(files.items(), key=lambda kv: kv[0]))


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def _files_equal(src: Path, dst: Path) -> bool:
    if not dst.is_file():
        return False
    if src.stat().st_size != dst.stat().st_size:
        return False
    return _sha256(src) == _sha256(dst)


def _prune_empty_dirs(root: Path) -> None:
    if not root.exists():
        return
    dirs = [p for p in root.rglob("*") if p.is_dir()]
    for d in sorted(dirs, key=lambda p: len(p.parts), reverse=True):
        try:
            d.rmdir()
        except OSError:
            pass


def mirror_source_files(source_files: dict[str, Path], target_root: Path, plan_only: bool = False) -> dict[str, Any]:
    existing: dict[str, Path] = {}
    if target_root.exists():
        for p in target_root.rglob("*"):
            if p.is_file():
                existing[p.relative_to(target_root).as_posix()] = p

    created = 0
    updated = 0
    unchanged = 0
    deleted = 0

    if not plan_only:
        target_root.mkdir(parents=True, exist_ok=True)

    source_keys = set(source_files.keys())
    existing_keys = set(existing.keys())

    for rel in sorted(source_keys):
        src = source_files[rel]
        dst = target_root / rel
        if rel in existing and _files_equal(src, existing[rel]):
            unchanged += 1
            continue
        if rel in existing:
            updated += 1
        else:
            created += 1
        if plan_only:
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)

    to_delete = sorted(existing_keys - source_keys)
    deleted = len(to_delete)
    if not plan_only:
        for rel in to_delete:
            try:
                (target_root / rel).unlink()
            except FileNotFoundError:
                pass
        _prune_empty_dirs(target_root)

    return {
        "scanned_files": len(source_files),
        "created_files": created,
        "updated_files": updated,
        "unchanged_files": unchanged,
        "deleted_files": deleted,
    }


def _decode_json_or_text(raw: bytes) -> Any:
    text = raw.decode("utf-8", errors="replace")
    try:
        return json.loads(text)
    except Exception:
        return text


def _http_json_request(
    *,
    method: str,
    url: str,
    timeout_sec: int,
    headers: dict[str, str] | None = None,
    payload: dict[str, Any] | None = None,
) -> tuple[int, Any]:
    req_headers = {"Content-Type": "application/json"}
    if headers:
        req_headers.update(headers)

    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(url=url, data=data, headers=req_headers, method=method)

    try:
        with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
            body = resp.read()
            return int(resp.status), _decode_json_or_text(body)
    except urllib.error.HTTPError as e:
        body = e.read() if e.fp else b""
        return int(e.code), _decode_json_or_text(body)


def trigger_admin_sync(
    settings: OrchestratorSettings,
    source: SourceSpec,
    sync_rel_path: str,
    *,
    sync_dry_run: bool,
) -> dict[str, Any]:
    api_key = os.getenv(settings.admin_api_key_env, "").strip()
    if not api_key:
        raise RuntimeError(f"Missing API key in env var: {settings.admin_api_key_env}")

    payload: dict[str, Any] = {
        "path": sync_rel_path,
        "source_type": source.source_type,
        "delete_missing": bool(source.delete_missing),
        "dry_run": bool(sync_dry_run),
    }
    if source.author:
        payload["author"] = source.author
    if source.year is not None:
        payload["year"] = source.year

    status, body = _http_json_request(
        method="POST",
        url=f"{settings.admin_base_url}/v1/admin/sync",
        timeout_sec=settings.request_timeout_sec,
        headers={"X-API-Key": api_key},
        payload=payload,
    )
    ok = status == 200 and isinstance(body, dict) and bool(body.get("ok"))
    return {"ok": ok, "http_status": status, "payload": payload, "response": body}


def fetch_coverage_actions(settings: OrchestratorSettings) -> dict[str, Any]:
    api_key = os.getenv(settings.admin_api_key_env, "").strip()
    if not api_key:
        raise RuntimeError(f"Missing API key in env var: {settings.admin_api_key_env}")

    status, body = _http_json_request(
        method="GET",
        url=f"{settings.admin_base_url}/v1/admin/coverage-actions",
        timeout_sec=settings.request_timeout_sec,
        headers={"X-API-Key": api_key},
        payload=None,
    )
    ok = status == 200 and isinstance(body, dict) and bool(body.get("ok"))
    return {"ok": ok, "http_status": status, "response": body}


def _select_sources(all_sources: list[SourceSpec], only: set[str] | None) -> list[SourceSpec]:
    if not only:
        return all_sources
    selected = [s for s in all_sources if s.name in only]
    missing = sorted(only - {s.name for s in selected})
    if missing:
        raise ValueError(f"Unknown source names in --only: {', '.join(missing)}")
    return selected


def run_orchestrator(
    config: OrchestratorConfig,
    *,
    only: set[str] | None = None,
    plan_only: bool = False,
    skip_sync: bool = False,
    sync_dry_run: bool = False,
) -> dict[str, Any]:
    settings = config.settings
    selected_sources = _select_sources(config.sources, only)
    started_at = datetime.now(timezone.utc).isoformat()

    if not plan_only:
        (settings.ingest_root / settings.ingest_live_subdir).mkdir(parents=True, exist_ok=True)

    source_results: list[dict[str, Any]] = []
    ok = True

    for source in selected_sources:
        source_result: dict[str, Any] = {
            "name": source.name,
            "repo_path": str(source.repo_path),
            "source_type": source.source_type,
        }
        try:
            source_files = collect_source_files(source)
            target_root = (settings.ingest_root / settings.ingest_live_subdir / source.target_subdir).resolve(
                strict=False
            )
            source_result["target_path"] = str(target_root)
            source_result["export"] = mirror_source_files(source_files, target_root, plan_only=plan_only)

            sync_rel_path = _join_rel_posix(settings.ingest_live_subdir, source.target_subdir)
            source_result["sync_rel_path"] = sync_rel_path

            if plan_only:
                source_result["sync"] = {"skipped": True, "reason": "plan_only"}
            elif skip_sync:
                source_result["sync"] = {"skipped": True, "reason": "skip_sync"}
            else:
                sync_result = trigger_admin_sync(
                    settings=settings,
                    source=source,
                    sync_rel_path=sync_rel_path,
                    sync_dry_run=sync_dry_run,
                )
                source_result["sync"] = sync_result
                if not sync_result.get("ok"):
                    ok = False
        except Exception as e:
            source_result["error"] = str(e)
            ok = False

        source_results.append(source_result)

    coverage_result: dict[str, Any] | None = None
    if settings.fetch_coverage_actions and not plan_only and not skip_sync:
        try:
            coverage_result = fetch_coverage_actions(settings)
            if not coverage_result.get("ok"):
                ok = False
        except Exception as e:
            coverage_result = {"ok": False, "error": str(e)}
            ok = False

    return {
        "ok": ok,
        "started_at": started_at,
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "plan_only": bool(plan_only),
        "skip_sync": bool(skip_sync),
        "sync_dry_run": bool(sync_dry_run),
        "source_count": len(selected_sources),
        "sources": source_results,
        "coverage_actions": coverage_result,
    }


def _parse_only(value: str | None) -> set[str] | None:
    if not value:
        return None
    parts = [p.strip() for p in value.split(",")]
    cleaned = {p for p in parts if p}
    return cleaned or None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True, help="Path to TOML config.")
    parser.add_argument("--only", default="", help="Comma-separated source names.")
    parser.add_argument("--plan-only", action="store_true", default=False, help="Analyze only, no file writes, no sync.")
    parser.add_argument("--skip-sync", action="store_true", default=False, help="Mirror files but skip /v1/admin/sync.")
    parser.add_argument("--sync-dry-run", action="store_true", default=False, help="Set dry_run=true for /v1/admin/sync calls.")
    args = parser.parse_args()

    config = load_config(args.config)
    result = run_orchestrator(
        config,
        only=_parse_only(args.only),
        plan_only=bool(args.plan_only),
        skip_sync=bool(args.skip_sync),
        sync_dry_run=bool(args.sync_dry_run),
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if not result.get("ok"):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
