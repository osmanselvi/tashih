"""Öneri uç noktaları: kabul / reddet / geri al."""
from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Suggestion
from ..schemas import PageOut, SuggestionPatch, SuggestionResult
from ..services.geometry import shift_words
from .common import (
    add_changelog,
    get_document_or_404,
    page_to_out,
    recompute_status,
    suggestion_to_out,
)

router = APIRouter(prefix="/api/suggestions", tags=["suggestions"])

log = logging.getLogger("tashih.suggestions")


def _shift_offsets(page, after: int, delta: int, exclude_id: int) -> None:
    """after noktasından itibaren diğer önerilerin ofsetlerini kaydırır."""
    for other in page.suggestions:
        if other.id == exclude_id:
            continue
        if other.start >= after:
            other.start += delta
            other.end += delta


def _shift_geometry(page, start: int, end: int, replacement: str, old_text: str) -> None:
    """Sayfa sözcük ofsetlerini yeni metne hizalar.

    Geometri metinle aynı ofsetleri paylaşır; düzeltme sonrası kaydırılmazsa
    tıklama→kelime eşleşmesi bozulur.
    """
    if not page.words:
        return
    try:
        geom = json.loads(page.words)
    except (TypeError, ValueError):
        return
    if not isinstance(geom, dict):
        return
    shift_words(geom, start, end, replacement, old_text)
    page.words = json.dumps(geom)


def apply_suggestion(db: Session, sug: Suggestion) -> None:
    """Öneriyi sayfa metnine uygular (kabul)."""
    page = sug.page
    doc = page.document
    text = page.text
    start, end = sug.start, sug.end

    if not (0 <= start <= end <= len(text)) or text[start:end] != sug.original:
        # Ofsetler güncellenmiş olabilir; metinde ara
        if sug.original == "" and 0 <= start <= len(text):
            start = end = start
        else:
            found = text.find(sug.original)
            if found == -1:
                raise HTTPException(
                    status_code=409,
                    detail="Öneri artık metinle eşleşmiyor. Sayfayı yenileyin.",
                )
            start, end = found, found + len(sug.original)

    new_text = text[:start] + sug.replacement + text[end:]
    delta = len(sug.replacement) - (end - start)

    sug.start, sug.end = start, end
    _shift_offsets(page, after=end, delta=delta, exclude_id=sug.id)
    _shift_geometry(page, start, end, sug.replacement, text)
    page.text = new_text
    add_changelog(
        db, doc, page, sug.original, sug.replacement, source=sug.source or "ai"
    )


def unapply_suggestion(db: Session, sug: Suggestion) -> None:
    """Daha önce kabul edilen öneriyi geri alır."""
    page = sug.page
    doc = page.document
    text = page.text
    start = sug.start
    applied_end = start + len(sug.replacement)

    if not (0 <= start <= applied_end <= len(text)) or text[start:applied_end] != sug.replacement:
        found = text.find(sug.replacement) if sug.replacement else -1
        if sug.replacement == "" and 0 <= start <= len(text):
            start, applied_end = start, start
        elif found == -1:
            raise HTTPException(
                status_code=409,
                detail="Değişiklik geri alınamadı (metin değişmiş). Sayfayı yenileyin.",
            )
        elif text.count(sug.replacement) > 1:
            # Metin birden çok yerde aynı metni içeriyor: yanlış yere
            # uygulamak metni bozar, bu yüzden geri alma yapılmaz.
            raise HTTPException(
                status_code=409,
                detail=(
                    "Değişiklik geri alınamadı (metin değişmiş). "
                    "İşareti silebilir, düzeltmeyi elle yapabilirsiniz."
                ),
            )
        else:
            start, applied_end = found, found + len(sug.replacement)

    new_text = text[:start] + sug.original + text[applied_end:]
    delta = len(sug.original) - len(sug.replacement)

    _shift_offsets(page, after=applied_end, delta=delta, exclude_id=sug.id)
    _shift_geometry(page, start, applied_end, sug.original, text)
    page.text = new_text
    add_changelog(
        db, doc, page, sug.replacement, sug.original, source=sug.source or "ai"
    )


@router.patch("/{suggestion_id}", response_model=SuggestionResult)
def patch_suggestion(
    suggestion_id: int,
    payload: SuggestionPatch,
    db: Session = Depends(get_db),
):
    sug = db.get(Suggestion, suggestion_id)
    if sug is None:
        raise HTTPException(status_code=404, detail="Öneri bulunamadı.")

    target = payload.status
    current = sug.status

    if target != current:
        if target == "accepted":
            apply_suggestion(db, sug)
            sug.status = "accepted"
        elif target == "pending" and current == "accepted":
            unapply_suggestion(db, sug)
            sug.status = "pending"
        else:  # rejected → pending / pending → rejected / rejected → accepted
            if target == "accepted":
                apply_suggestion(db, sug)
            sug.status = target

    doc = sug.page.document
    db.flush()
    recompute_status(db, doc)
    db.commit()
    db.refresh(sug)
    db.refresh(sug.page)

    return SuggestionResult(
        suggestion=suggestion_to_out(sug),
        page=page_to_out(sug.page),
    )


@router.delete("/{suggestion_id}")
def delete_suggestion(suggestion_id: int, db: Session = Depends(get_db)):
    """Öneriyi (veya musahhih işaretini) kalıcı olarak siler.

    Kabul edilmiş bir işaret silinirse önce metne geri alınır.
    """
    sug = db.get(Suggestion, suggestion_id)
    if sug is None:
        raise HTTPException(status_code=404, detail="Öneri bulunamadı.")

    page = sug.page
    doc = page.document

    if sug.status == "accepted":
        try:
            unapply_suggestion(db, sug)
        except HTTPException:
            # Metin sonradan değişmiş: işaret yine de kaldırılır, metne
            # dokunulmaz (yazarın isteği esas alınır).
            db.expire(sug, ["status"])
            log.warning(
                "İşaret %s silindi ancak düzeltme geri alınamadı (metin değişmiş).",
                sug.id,
            )

    db.delete(sug)
    db.flush()
    recompute_status(db, doc)
    db.commit()

    return {"ok": True}
