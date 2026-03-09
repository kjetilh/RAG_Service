from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from app.api.routes_chat import router as chat_router
from app.api.routes_ui import router as ui_router
from app.api.routes_admin import router as admin_router
from app.api.routes_cell import router as cell_router
from app.api.routes_interviews import router as interviews_router
from app.api.routes_research import router as research_router

app = FastAPI(title="Innovation RAG Service", version="0.1.0")


# Serve static assets
app.mount("/static", StaticFiles(directory="app/static"), name="static")
app.include_router(ui_router)
app.include_router(chat_router)
app.include_router(admin_router)
app.include_router(cell_router)
app.include_router(interviews_router)
app.include_router(research_router)

@app.get("/health")
def health():
    return {"ok": True}
