"""Pydantic şemaları (API sözleşmesi)."""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

DocStatus = Literal["extracted", "analyzing", "analyzed", "reviewing", "done"]
SuggestionStatus = Literal["pending", "accepted", "rejected"]
SuggestionKind = Literal[
    "spelling", "grammar", "punctuation", "ocr", "style", "manual"
]
CorrectionMutation = Literal["delete", "insert", "replace", "space", "join"]


class SuggestionOut(BaseModel):
    id: int
    page_id: int
    kind: str
    original: str
    replacement: str
    start: int
    end: int
    explanation: str
    status: str
    # Asıl PDF sayfasındaki konum: [x0, y0, x1, y1] (PDF puanları) veya null
    rect: list[float] | None = None
    # "ai" (kural/LLM önerisi) veya "manual" (yazar/musahhih işareti)
    source: str = "ai"
    # Manuel işaretlerin türü: delete|insert|replace|space|join
    mutation: str | None = None

    model_config = {"from_attributes": True}


class PageOut(BaseModel):
    id: int
    number: int
    text: str
    original_text: str
    has_text: bool
    # Sayfa ölçüleri (PDF puanları) — baloncuk konumlandırması için
    width: float | None = None
    height: float | None = None
    suggestions: list[SuggestionOut] = []

    model_config = {"from_attributes": True}


class DocumentSummary(BaseModel):
    id: int
    filename: str
    status: str
    page_count: int
    created_at: datetime
    pending_count: int = 0


class DocumentDetail(DocumentSummary):
    pages: list[PageOut] = []
    analyzer_mode: str | None = None


class SuggestionResult(BaseModel):
    suggestion: SuggestionOut
    page: PageOut


class ChangeLogEntry(BaseModel):
    id: int
    page_number: int
    old_text: str
    new_text: str
    source: str
    created_at: datetime

    model_config = {"from_attributes": True}


class SuggestionPatch(BaseModel):
    status: SuggestionStatus


class PagePut(BaseModel):
    text: str = Field(min_length=0)


class AnalyzeRequest(BaseModel):
    page_numbers: list[int] | None = None


class ExportRequest(BaseModel):
    format: Literal["txt", "md", "docx"] = "txt"


class CorrectionCreate(BaseModel):
    """Yazar/musahhih işareti: sayfa görselinde tıklanan noktadan üretilir."""

    page_id: int
    start: int
    end: int
    mutation: CorrectionMutation = "replace"
    # Değiştirme/ekleme için yeni metin (diğer türlerde yok sayılır)
    replacement: str = ""
    # Kullanıcının notu (isteğe bağlı)
    explanation: str = ""


class WordAtPointRequest(BaseModel):
    x: float
    y: float


class WordHit(BaseModel):
    found: bool
    start: int = 0
    end: int = 0
    text: str = ""
    rect: list[float] | None = None
