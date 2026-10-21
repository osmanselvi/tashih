"""Tashih — PDF metin musahhihlik çalışma masası."""
from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

from .api import documents, suggestions
from .config import BASE_DIR, ensure_dirs
from .db import init_db

DIST_DIR = (BASE_DIR.parent / "web" / "dist").resolve()


@asynccontextmanager
async def lifespan(_: FastAPI):
    ensure_dirs()
    init_db()
    try:
        # Eski kayıtlara sayfa ölçüleri ve baloncuk konumlarını geriye dönük ekle
        from .services.backfill import backfill_geometry

        backfill_geometry()
    except Exception:  # noqa: BLE001 — açılışı engellememeli
        import logging

        logging.getLogger("tashih").exception("Geriye dönük konum tamamlama başarısız")
    yield


app = FastAPI(
    title="Tashih",
    description="PDF metinleri için musahhihlik çalışma masası.",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(documents.router)
app.include_router(suggestions.router)


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/{full_path:path}", include_in_schema=False)
def spa(full_path: str):
    """Derlenmiş frontend'i (web/dist) sunar; bilinmeyen yollar index.html'e düşer."""
    if full_path.startswith("api/"):
        return JSONResponse({"detail": "Bulunamadı"}, status_code=404)

    if DIST_DIR.is_dir():
        if full_path:
            candidate = (DIST_DIR / full_path).resolve()
            try:
                candidate.relative_to(DIST_DIR)
            except ValueError:
                candidate = None
            if candidate is not None and candidate.is_file():
                return FileResponse(candidate)
        index = DIST_DIR / "index.html"
        if index.is_file():
            return FileResponse(index)

    return JSONResponse({"detail": "Bulunamadı"}, status_code=404)
