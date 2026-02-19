from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from app.scripts_adapter import rebuild_index, ingest_folder

router = APIRouter()

class RebuildRequest(BaseModel):
    confirm: bool = False

@router.post("/v1/admin/rebuild")
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

@router.post("/v1/admin/ingest")
def admin_ingest(req: IngestRequest):
    ingest_folder(path=req.path, source_type=req.source_type, author=req.author, year=req.year)
    return {"ok": True}
