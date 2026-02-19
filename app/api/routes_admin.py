from pathlib import Path
import secrets

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel

from app.scripts_adapter import rebuild_index, ingest_folder
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
