from fastapi import APIRouter
from fastapi.responses import FileResponse
from pathlib import Path

router = APIRouter()

@router.get("/", include_in_schema=False)
def root():
    static_dir = Path(__file__).resolve().parents[1] / "static"
    return FileResponse(static_dir / "chat.html")


@router.get("/prompt-admin", include_in_schema=False)
def prompt_admin():
    static_dir = Path(__file__).resolve().parents[1] / "static"
    return FileResponse(static_dir / "prompt_admin.html")
