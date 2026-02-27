from pathlib import Path
import secrets
from datetime import datetime

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.exc import SQLAlchemyError

from app.rag.generate.prompt_config_store import (
    PromptRuntimeConfig,
    get_runtime_config,
    resolve_effective_paths,
    resolve_prompt_path,
    upsert_runtime_config,
)
from app.scripts_adapter import rebuild_index, ingest_folder, sync_folder
from app.settings import settings

router = APIRouter()


def _require_admin_api_key(
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> None:
    if not settings.admin_api_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Admin API is disabled: ADMIN_API_KEY is not configured.",
        )

    if x_api_key is None or not secrets.compare_digest(x_api_key, settings.admin_api_key):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing admin API key.",
        )


def _validated_ingest_path(requested_path: str) -> str:
    root = Path(settings.ingest_root).expanduser().resolve(strict=False)
    requested = Path(requested_path).expanduser()
    if requested.is_absolute():
        candidate = requested.resolve(strict=False)
    else:
        candidate = (root / requested).resolve(strict=False)

    if candidate != root and root not in candidate.parents:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"path must be under ingest root: {root}",
        )

    return str(candidate)


class RebuildRequest(BaseModel):
    confirm: bool = False


@router.post("/v1/admin/rebuild", dependencies=[Depends(_require_admin_api_key)])
def admin_rebuild(req: RebuildRequest):
    if not req.confirm:
        raise HTTPException(status_code=400, detail="Set confirm=true to rebuild index tables.")
    rebuild_index()
    return {"ok": True}


class IngestRequest(BaseModel):
    path: str
    source_type: str = "unknown"
    author: str | None = None
    year: int | None = None


@router.post("/v1/admin/ingest", dependencies=[Depends(_require_admin_api_key)])
def admin_ingest(req: IngestRequest):
    ingest_folder(
        path=_validated_ingest_path(req.path),
        source_type=req.source_type,
        author=req.author,
        year=req.year,
    )
    return {"ok": True}


class SyncRequest(BaseModel):
    path: str
    source_type: str | None = None
    author: str | None = None
    year: int | None = None
    delete_missing: bool = True
    dry_run: bool = False


@router.post("/v1/admin/sync", dependencies=[Depends(_require_admin_api_key)])
def admin_sync(req: SyncRequest):
    if req.delete_missing and req.source_type is None:
        raise HTTPException(status_code=400, detail="source_type must be set when delete_missing=true")
    summary = sync_folder(
        path=_validated_ingest_path(req.path),
        source_type=req.source_type,
        author=req.author,
        year=req.year,
        delete_missing=req.delete_missing,
        dry_run=req.dry_run,
    )
    return {"ok": len(summary.get("errors", [])) == 0, "summary": summary}


class PromptConfigResponse(BaseModel):
    system_persona_path: str | None
    answer_template_path: str | None
    effective_system_persona_path: str
    effective_answer_template_path: str
    system_persona_source: str
    answer_template_source: str
    system_persona_resolved_path: str
    answer_template_resolved_path: str
    system_persona_bytes: int
    answer_template_bytes: int
    version: int
    updated_by: str | None = None
    change_note: str | None = None
    updated_at: datetime | None = None


class PromptConfigUpdateRequest(BaseModel):
    system_persona_path: str | None = None
    answer_template_path: str | None = None
    updated_by: str | None = None
    change_note: str | None = None


def _normalize_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def _prompt_file_info(path_value: str, label: str) -> tuple[str, int]:
    resolved = resolve_prompt_path(path_value).resolve(strict=False)
    if not resolved.is_file():
        raise HTTPException(status_code=400, detail=f"{label} not found: {resolved}")
    size = resolved.stat().st_size
    if size <= 0:
        raise HTTPException(status_code=400, detail=f"{label} is empty: {resolved}")
    return str(resolved), size


def _build_prompt_config_response(runtime_cfg: PromptRuntimeConfig) -> PromptConfigResponse:
    system_path, answer_path, system_source, answer_source = resolve_effective_paths(runtime_cfg)
    system_resolved, system_bytes = _prompt_file_info(system_path, "system_persona_path")
    answer_resolved, answer_bytes = _prompt_file_info(answer_path, "answer_template_path")
    return PromptConfigResponse(
        system_persona_path=runtime_cfg.system_persona_path,
        answer_template_path=runtime_cfg.answer_template_path,
        effective_system_persona_path=system_path,
        effective_answer_template_path=answer_path,
        system_persona_source=system_source,
        answer_template_source=answer_source,
        system_persona_resolved_path=system_resolved,
        answer_template_resolved_path=answer_resolved,
        system_persona_bytes=system_bytes,
        answer_template_bytes=answer_bytes,
        version=runtime_cfg.version,
        updated_by=runtime_cfg.updated_by,
        change_note=runtime_cfg.change_note,
        updated_at=runtime_cfg.updated_at,
    )


@router.get(
    "/v1/admin/prompt-config",
    response_model=PromptConfigResponse,
    dependencies=[Depends(_require_admin_api_key)],
)
def admin_get_prompt_config():
    try:
        cfg = get_runtime_config()
        return _build_prompt_config_response(cfg)
    except HTTPException:
        raise
    except SQLAlchemyError as e:
        raise HTTPException(status_code=500, detail=f"Database error reading prompt config: {e}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put(
    "/v1/admin/prompt-config",
    response_model=PromptConfigResponse,
    dependencies=[Depends(_require_admin_api_key)],
)
def admin_update_prompt_config(req: PromptConfigUpdateRequest):
    provided_fields = req.model_fields_set
    if "system_persona_path" not in provided_fields and "answer_template_path" not in provided_fields:
        raise HTTPException(
            status_code=400,
            detail="Provide at least one of system_persona_path or answer_template_path.",
        )

    try:
        current = get_runtime_config()
        new_system_override = (
            _normalize_optional_text(req.system_persona_path)
            if "system_persona_path" in provided_fields
            else current.system_persona_path
        )
        new_answer_override = (
            _normalize_optional_text(req.answer_template_path)
            if "answer_template_path" in provided_fields
            else current.answer_template_path
        )

        proposed = PromptRuntimeConfig(
            system_persona_path=new_system_override,
            answer_template_path=new_answer_override,
            version=current.version,
            updated_by=current.updated_by,
            change_note=current.change_note,
            updated_at=current.updated_at,
        )

        # Validate proposed effective paths before persisting.
        _build_prompt_config_response(proposed)

        updated = upsert_runtime_config(
            system_persona_path=new_system_override,
            answer_template_path=new_answer_override,
            updated_by=_normalize_optional_text(req.updated_by) or "admin-api",
            change_note=_normalize_optional_text(req.change_note),
        )
        return _build_prompt_config_response(updated)
    except HTTPException:
        raise
    except SQLAlchemyError as e:
        raise HTTPException(status_code=500, detail=f"Database error writing prompt config: {e}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
