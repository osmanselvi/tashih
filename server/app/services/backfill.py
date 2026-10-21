"""Eski kayıtlar için sayfa ölçüleri, geometri ve öneri konumlarını tamamlar.

Yeni yüklemeler tüm geometriyi alır; bu modül önceden yüklenmiş belgelerde
eksik `width/height/words` ve `rect` alanlarını açılışta doldurur.

Yinelenen işi önlemek için yalnızca gerçekten eksik olan işler için PDF açılır:
rect'i dolu öneriler ve ölçüleri tam sayfalar atlanır. Bir türlü bulunamayan
konumlar "[]" ile işaretlenir; girdiler (PDF, metin, ofsetler) sabit olduğundan
sonuç da sabittir ve her açılışta yeniden aranmaz.
"""
from __future__ import annotations

import json
import logging

from sqlalchemy import select

from ..db import SessionLocal
from ..models import Document
from .geometry import PdfLocator, resolve_rect

log = logging.getLogger("tashih.backfill")


def backfill_geometry() -> None:
    db = SessionLocal()
    try:
        doc_ids = db.scalars(select(Document.id)).all()
        for doc_id in doc_ids:
            try:
                _backfill_document(db, doc_id)
            except Exception:
                log.exception("Belge %s için konum tamamlama başarısız", doc_id)
                db.rollback()
    finally:
        db.close()


def _backfill_document(db, doc_id: int) -> None:
    doc = db.get(Document, doc_id)
    if doc is None:
        return

    # Yalnız gerçekten eksik olan işler için PDF'i aç (rect'leri dolu bir
    # belge bir sonraki açılışta hiç iş yapmaz).
    need_size = [p for p in doc.pages if p.width is None or p.height is None]
    need_rect = [
        p for p in doc.pages if any(s.rect is None for s in p.suggestions)
    ]
    if not need_size and not need_rect:
        return

    with PdfLocator(doc.stored_path) as locator:
        # 1) Sayfa ölçüleri
        for page in need_size:
            size = locator.page_size(page.number)
            if size:
                page.width, page.height = size

        # 2) Eksik öneri konumları (yalnız rect'i eksik olan sayfalarda)
        for page in need_rect:
            geom = json.loads(page.words) if page.words else None
            if page.words is None:
                content = locator.page_content(page.number)
                if content is not None:
                    built_text, built_geom, _w, _h = content
                    if built_text == page.text:
                        # Metin birebir aynı → geometri hizalı kullanılabilir
                        page.words = json.dumps(built_geom)
                        geom = built_geom
                    # Farklıysa (eski çıkarım veya düzenlenmiş metin) hizalama
                    # kurulamaz; arama yedeğine düşülür ve yeniden denenmez.
            readable = locator.page_size(page.number) is not None
            for sug in page.suggestions:
                if sug.rect is not None:
                    continue
                rect = resolve_rect(
                    locator,
                    geom,
                    page.number,
                    page.text,
                    sug.start,
                    sug.end,
                    sug.original,
                )
                if rect:
                    sug.rect = json.dumps(rect)
                elif readable:
                    # PDF okunuyor ama konum bulunamıyor → sonucu işaretle ki
                    # her açılışta aynı arama tekrarlanmasın.
                    sug.rect = "[]"

    db.commit()
