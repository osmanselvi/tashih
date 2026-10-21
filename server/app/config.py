"""Uygulama ayarları (env değişkenlerinden okunur)."""
from __future__ import annotations

import os
from pathlib import Path

try:  # .env dosyası varsa yükle
    from dotenv import load_dotenv

    load_dotenv()
except Exception:  # pragma: no cover - dotenv opsiyonel
    pass

# server/ dizini
BASE_DIR = Path(__file__).resolve().parent.parent

DATA_DIR = Path(os.getenv("DATA_DIR", str(BASE_DIR / "data"))).resolve()
UPLOAD_DIR = DATA_DIR / "uploads"
PAGE_IMAGE_DIR = DATA_DIR / "pages"

DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{DATA_DIR / 'tashih.db'}")

LLM_API_KEY = os.getenv("LLM_API_KEY", "").strip()
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://api.openai.com/v1").rstrip("/")
LLM_MODEL = os.getenv("LLM_MODEL", "gpt-4o-mini")

MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "50"))
MAX_UPLOAD_BYTES = MAX_UPLOAD_MB * 1024 * 1024

# Sistem LANG değişkeni POSIX dil etiketi olabilir; sadece tr/en kabul et.
_lang = os.getenv("LANG", "tr").strip().lower()
DEFAULT_LANG = _lang if _lang in ("tr", "en") else "tr"

SUPPORTED_EXPORTS = ("txt", "md", "docx")


def ensure_dirs() -> None:
    for path in (DATA_DIR, UPLOAD_DIR, PAGE_IMAGE_DIR):
        path.mkdir(parents=True, exist_ok=True)
