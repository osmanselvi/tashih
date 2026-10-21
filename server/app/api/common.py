"""Seriileştirme yardımcıları ve ortak sorgular."""
from __future__ import annotations

import json

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import ChangeLog, Document, Page, Suggestion
from ..schemas import (
    ChangeLogEntry,
    DocumentDetail,
    DocumentSummary,
    PageOut,
    SuggestionOut,
)


def get_document_or_404(db: Session, document_id: int) -> Document:
    doc = db.get(Document, document_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Belge bulunamadı.")
    return doc


def get_page_or_404(db: Session, doc: Document, page_number: int) -> Page:
    page = next((p for p in doc.pages if p.number == page_number), None)
    if page is None:
        raise HTTPException(status_code=404, detail="Sayfa bulunamadı.")
    return page


def pending_count(doc: Document) -> int:
    return sum(
        1 for page in doc.pages for sug in page.suggestions if sug.status == "pending"
    )


def _load_rect(value: str | None) -> list[float] | None:
    if not value:
        return None
    try:
        parsed = json.loads(value)
    except (TypeError, ValueError):
        return None
    return parsed if isinstance(parsed, list) else None


def suggestion_to_out(sug: Suggestion) -> SuggestionOut:
    return SuggestionOut(
        id=sug.id,
        page_id=sug.page_id,
        kind=sug.kind,
        original=sug.original,
        replacement=sug.replacement,
        start=sug.start,
        end=sug.end,
        explanation=sug.explanation,
        status=sug.status,
        rect=_load_rect(sug.rect),
        source=sug.source or "ai",
        mutation=sug.mutation,
    )


def page_to_out(page: Page) -> PageOut:
    return PageOut(
        id=page.id,
        number=page.number,
        text=page.text,
        original_text=page.original_text,
        has_text=page.has_text,
        width=page.width,
        height=page.height,
        suggestions=[suggestion_to_out(s) for s in page.suggestions],
    )


def summary_to_out(doc: Document) -> DocumentSummary:
    return DocumentSummary(
        id=doc.id,
        filename=doc.filename,
        status=doc.status,
        page_count=doc.page_count,
        created_at=doc.created_at,
        pending_count=pending_count(doc),
    )


def detail_to_out(doc: Document) -> DocumentDetail:
    return DocumentDetail(
        **summary_to_out(doc).model_dump(),
        pages=[page_to_out(p) for p in doc.pages],
        analyzer_mode=doc.analyzer_mode,
    )


def add_changelog(
    db: Session,
    doc: Document,
    page: Page,
    old_text: str,
    new_text: str,
    source: str,
) -> None:
    db.add(
        ChangeLog(
            document_id=doc.id,
            page_id=page.id,
            page_number=page.number,
            old_text=old_text,
            new_text=new_text,
            source=source,
        )
    )


def recompute_status(db: Session, doc: Document) -> None:
    """İnceleme durumunu öneriler ve değişiklik geçmişine göre tazeler."""
    total = sum(len(page.suggestions) for page in doc.pages)
    pending = pending_count(doc)
    changes = db.scalar(
        select(ChangeLog.id).where(ChangeLog.document_id == doc.id).limit(1)
    )

    if total and pending == 0:
        doc.status = "done"
    elif changes is not None:
        doc.status = "reviewing"
    elif total:
        doc.status = "analyzed"
