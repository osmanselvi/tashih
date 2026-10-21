"""Belge (PDF) uç noktaları: yükleme, okuma, sayfa görüntüleri, dışa aktarma."""
from __future__ import annotations

import json
import re
import shutil
import uuid
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..config import MAX_UPLOAD_BYTES, PAGE_IMAGE_DIR, UPLOAD_DIR
from ..db import get_db
from ..models import ChangeLog, Document, Page, Suggestion
from ..schemas import (
    AnalyzeRequest,
    ChangeLogEntry,
    CorrectionCreate,
    DocumentDetail,
    DocumentSummary,
    ExportRequest,
    PageOut,
    PagePut,
    SuggestionResult,
    WordAtPointRequest,
    WordHit,
)
from ..services.analyzer import analyze_page
from ..services.corrections import build_corrections_json
from ..services.exporter import export_document
from ..services.extractor import extract_pdf
from ..services.geometry import (
    PdfLocator,
    resolve_rect,
    word_at_point as find_word_at_point,
)
from .common import (
    add_changelog,
    detail_to_out,
    get_document_or_404,
    get_page_or_404,
    page_to_out,
    recompute_status,
    suggestion_to_out,
    summary_to_out,
)
from .suggestions import apply_suggestion

router = APIRouter(prefix="/api/documents", tags=["documents"])

_MEDIA_TYPES = {
    "txt": "text/plain; charset=utf-8",
    "md": "text/markdown; charset=utf-8",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


@router.get("", response_model=list[DocumentSummary])
def list_documents(db: Session = Depends(get_db)):
    docs = db.scalars(select(Document).order_by(Document.id.desc())).all()
    return [summary_to_out(doc) for doc in docs]


@router.post("", response_model=DocumentDetail)
async def upload_document(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    filename = file.filename or ""
    if not filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Yalnızca PDF dosyaları yüklenebilir.")

    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Dosya boş.")
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Dosya boyutu çok büyük.")

    stored_path = UPLOAD_DIR / f"{uuid.uuid4().hex}.pdf"
    stored_path.write_bytes(data)

    doc = Document(filename=filename, stored_path=str(stored_path), status="extracted")
    db.add(doc)
    db.flush()  # id al

    try:
        extracted = extract_pdf(stored_path, PAGE_IMAGE_DIR / str(doc.id))
    except Exception as exc:
        db.rollback()
        stored_path.unlink(missing_ok=True)
        raise HTTPException(
            status_code=422, detail=f"PDF okunamadı: {exc}"
        ) from exc

    if not extracted:
        db.rollback()
        stored_path.unlink(missing_ok=True)
        raise HTTPException(status_code=422, detail="PDF'de sayfa bulunamadı.")

    for item in extracted:
        db.add(
            Page(
                document_id=doc.id,
                number=item["number"],
                original_text=item["text"],
                text=item["text"],
                has_text=item["has_text"],
                width=item["width"],
                height=item["height"],
                words=item["words"],
            )
        )
    doc.page_count = len(extracted)
    doc.status = "extracted"
    db.commit()
    db.refresh(doc)
    return detail_to_out(doc)


@router.get("/{doc_id}", response_model=DocumentDetail)
def get_document(doc_id: int, db: Session = Depends(get_db)):
    return detail_to_out(get_document_or_404(db, doc_id))


@router.delete("/{doc_id}")
def delete_document(doc_id: int, db: Session = Depends(get_db)):
    doc = get_document_or_404(db, doc_id)
    Path(doc.stored_path).unlink(missing_ok=True)
    shutil.rmtree(PAGE_IMAGE_DIR / str(doc.id), ignore_errors=True)
    # Değişiklik geçmişi de belgeyle birlikte silinir
    db.execute(delete(ChangeLog).where(ChangeLog.document_id == doc.id))
    db.delete(doc)
    db.commit()
    return {"ok": True}


@router.get("/{doc_id}/pages/{page_number}/image")
def get_page_image(doc_id: int, page_number: int, db: Session = Depends(get_db)):
    doc = get_document_or_404(db, doc_id)
    get_page_or_404(db, doc, page_number)
    image_path = PAGE_IMAGE_DIR / str(doc.id) / f"page_{page_number}.png"
    if not image_path.is_file():
        raise HTTPException(status_code=404, detail="Sayfa görüntüsü bulunamadı.")
    return FileResponse(image_path, media_type="image/png")


@router.put("/{doc_id}/pages/{page_number}", response_model=PageOut)
def update_page_text(
    doc_id: int,
    page_number: int,
    payload: PagePut,
    db: Session = Depends(get_db),
):
    doc = get_document_or_404(db, doc_id)
    page = get_page_or_404(db, doc, page_number)

    new_text = payload.text
    if new_text != page.text:
        old_text = page.text
        page.text = new_text
        # Elle yapılan düzenleme eski ofsetlere dayanan bekleyen önerileri geçersiz kılar
        for sug in list(page.suggestions):
            if sug.status == "pending":
                db.delete(sug)
        # Sözcük ofsetleri yeni metinle hizalı değil: işaretleme arama yedeğine düşer
        if page.words:
            try:
                geom = json.loads(page.words)
                if isinstance(geom, dict):
                    geom["aligned"] = False
                    page.words = json.dumps(geom)
                else:
                    page.words = None
            except (TypeError, ValueError):
                page.words = None
        add_changelog(db, doc, page, old_text, new_text, source="manual")

    db.flush()
    recompute_status(db, doc)
    db.commit()
    db.refresh(page)
    return page_to_out(page)


_MANUAL_EXPLANATIONS = {
    "delete": "Yazar işareti: metin silindi.",
    "replace": "Yazar işareti: metin değiştirildi.",
    "insert": "Yazar işareti: metin eklendi.",
    "space": "Yazar işareti: boşluk eklendi.",
    "join": "Yazar işareti: kelimeler birleştirildi.",
}


@router.post("/{doc_id}/corrections", response_model=SuggestionResult)
def create_correction(
    doc_id: int,
    payload: CorrectionCreate,
    db: Session = Depends(get_db),
):
    """Yazar/musahhih işareti oluşturur.

    Düzeltme, sayfa görselinde tıklanan noktadaki kelimeye göre üretilir;
    işaret metne hemen uygulanır (kabul edilmiş sayılır) ve sayfa üzerinde
    baloncuk olarak gösterilir.
    """
    doc = get_document_or_404(db, doc_id)
    page = next((p for p in doc.pages if p.id == payload.page_id), None)
    if page is None:
        raise HTTPException(status_code=404, detail="Sayfa bulunamadı.")

    text = page.text
    start, end = payload.start, payload.end
    if not (0 <= start <= end <= len(text)):
        raise HTTPException(status_code=400, detail="Konum sayfa metni dışında.")

    mutation = payload.mutation
    if mutation in ("insert", "space"):
        start = end = payload.start
        original = ""
        replacement = payload.replacement if mutation == "insert" else " "
        if mutation == "insert" and not replacement.strip():
            raise HTTPException(status_code=400, detail="Eklenecek metin boş.")
    elif mutation == "delete":
        original = text[start:end]
        if not original.strip():
            raise HTTPException(status_code=400, detail="Silinecek metin boş.")
        # Kelimenin ardındaki (yoksa önündeki) tek boşluğu da sil
        # → metinde çift boşluk ya da satır başı boşluk kalmaz
        tail = re.match(r"[ \t\u00a0]", text[end:])
        if tail:
            end = end + 1
        elif start > 0 and text[start - 1] in " \t\u00a0":
            start = start - 1
        original = text[start:end]
        replacement = ""
    elif mutation == "join":
        word = text[start:end]
        core = word.rstrip()
        if not core.strip():
            raise HTTPException(status_code=400, detail="Birleştirilecek kelime boş.")
        if len(core) != len(word):
            end = start + len(core)
        # Yalnız satır içi boşluklar birleştirilebilir (satır sonu birleşmez)
        tail = re.match(r"[ \t\u00a0]+", text[end:])
        if not tail:
            raise HTTPException(
                status_code=400,
                detail="Bu kelimenin ardında birleştirilecek boşluk yok.",
            )
        # Kelime + aradaki boşluk → yalnız kelime (boşluk kaldırılır)
        end = end + tail.end()
        original = text[start:end]
        replacement = core
    else:  # replace
        original = text[start:end]
        replacement = payload.replacement
        if not original.strip() or not replacement:
            raise HTTPException(
                status_code=400, detail="Değiştirme için metin gerekli."
            )

    # Konum: asıl PDF sayfasındaki kutu (hizalı geometri, yoksa PDF araması)
    geom = json.loads(page.words) if page.words else None
    rect = resolve_rect(None, geom, page.number, text, start, end, original)
    if rect is None:
        with PdfLocator(doc.stored_path) as locator:
            rect = resolve_rect(
                locator, geom, page.number, text, start, end, original
            )

    sug = Suggestion(
        document_id=doc.id,
        page_id=page.id,
        kind="manual",
        original=original,
        replacement=replacement,
        start=start,
        end=end,
        explanation=payload.explanation or _MANUAL_EXPLANATIONS.get(mutation, ""),
        status="pending",
        rect=json.dumps(rect) if rect else None,
        source="manual",
        mutation=mutation,
    )
    db.add(sug)
    db.flush()

    # Musahhih işareti doğrudan uygulanır: metin güncellenir, geri alınabilir.
    apply_suggestion(db, sug)
    sug.status = "accepted"

    db.flush()
    recompute_status(db, doc)
    db.commit()
    db.refresh(sug)
    db.refresh(sug.page)
    return SuggestionResult(
        suggestion=suggestion_to_out(sug),
        page=page_to_out(sug.page),
    )


@router.post("/{doc_id}/pages/{page_number}/word-at", response_model=WordHit)
def word_at_point_endpoint(
    doc_id: int,
    page_number: int,
    payload: WordAtPointRequest,
    db: Session = Depends(get_db),
):
    """Sayfa görselinde tıklanan noktadaki kelimeyi bulur (musahhih işareti için)."""
    doc = get_document_or_404(db, doc_id)
    page = get_page_or_404(db, doc, page_number)

    geom = json.loads(page.words) if page.words else None
    hit = find_word_at_point(geom, payload.x, payload.y, page.text)
    if hit is None:
        # Geometri hizasız eski kayıtlar: PDF metin katmanından bul
        with PdfLocator(doc.stored_path) as locator:
            hit = locator.word_at(page.number, payload.x, payload.y, page.text)
    if hit is None:
        return WordHit(found=False)
    return WordHit(found=True, **hit)


@router.get("/{doc_id}/corrections.json")
def export_corrections_json(doc_id: int, db: Session = Depends(get_db)):
    """Musahhih işaretlerini (ve yapay zekâ önerilerini) JSON'a aktarır.

    Biçim, masaüstü "Musahhih" uygulamasının okuduğu şemayla uyumludur:
    `corrections` yazar işaretlerini, `aiSuggestions` ise önerileri taşır.
    """
    doc = get_document_or_404(db, doc_id)
    content = build_corrections_json(doc)
    stem = Path(doc.filename).stem or f"belge-{doc.id}"
    filename = f"{stem}_tashih-{datetime.now().strftime('%Y%m%d-%H%M%S')}.json"
    return Response(
        content=content,
        media_type="application/json; charset=utf-8",
        headers={
            "Content-Disposition": (
                f'attachment; filename="{filename}"; '
                f"filename*=UTF-8''{quote(filename)}"
            )
        },
    )


@router.get("/{doc_id}/changelog", response_model=list[ChangeLogEntry])
def get_changelog(doc_id: int, db: Session = Depends(get_db)):
    get_document_or_404(db, doc_id)
    entries = db.scalars(
        select(ChangeLog)
        .where(ChangeLog.document_id == doc_id)
        .order_by(ChangeLog.id.asc())
    ).all()
    return [
        ChangeLogEntry(
            id=e.id,
            page_number=e.page_number,
            old_text=e.old_text,
            new_text=e.new_text,
            source=e.source,
            created_at=e.created_at,
        )
        for e in entries
    ]


@router.post("/{doc_id}/export")
def export_document_endpoint(
    doc_id: int,
    payload: ExportRequest,
    db: Session = Depends(get_db),
):
    doc = get_document_or_404(db, doc_id)
    pages = [(page.number, page.text) for page in doc.pages]
    try:
        content = export_document(pages, payload.format)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    filename = f"tashih-belge-{doc.id}.{payload.format}"
    return Response(
        content=content,
        media_type=_MEDIA_TYPES[payload.format],
        headers={
            "Content-Disposition": (
                f'attachment; filename="{filename}"; '
                f"filename*=UTF-8''{quote(filename)}"
            )
        },
    )


@router.post("/{doc_id}/analyze", response_model=DocumentDetail)
def analyze_document(
    doc_id: int,
    payload: AnalyzeRequest | None = None,
    db: Session = Depends(get_db),
):
    doc = get_document_or_404(db, doc_id)
    targets = [page for page in doc.pages if page.has_text and page.text.strip()]
    if payload and payload.page_numbers:
        wanted = set(payload.page_numbers)
        targets = [page for page in targets if page.number in wanted]
    if not targets:
        raise HTTPException(
            status_code=400,
            detail="Analiz edilecek metinli sayfa yok (taranmış sayfa olabilir).",
        )

    mode = "heuristic"
    with PdfLocator(doc.stored_path) as locator:
        for page in targets:
            # Yeniden analiz: önceki bekleyen önerileri temizle
            for sug in list(page.suggestions):
                if sug.status == "pending":
                    db.delete(sug)
            drafts, page_mode = analyze_page(page.text)
            mode = page_mode
            if page.words is None:
                # Eski kayıt: geometri yoksa analiz sırasında bir kez kur ve
                # sakla — sonraki analizlerde ve açılış backfill'inde
                # tekrar kurulmasın (yalnız metin birebir örtüşüyorsa).
                content = locator.page_content(page.number)
                if content is not None and content[0] == page.text:
                    page.words = json.dumps(content[1])
            geom = json.loads(page.words) if page.words else None
            for draft in drafts:
                # Düzeltme, asıl PDF sayfasında konumlandırılır (OCR yok)
                rect = resolve_rect(
                    locator,
                    geom,
                    page.number,
                    page.text,
                    draft["start"],
                    draft["end"],
                    draft["original"],
                )
                db.add(
                    Suggestion(
                        document_id=doc.id,
                        page_id=page.id,
                        kind=draft["kind"],
                        original=draft["original"],
                        replacement=draft["replacement"],
                        start=draft["start"],
                        end=draft["end"],
                        explanation=draft["explanation"],
                        status="pending",
                        rect=json.dumps(rect) if rect else None,
                    )
                )

    doc.analyzer_mode = mode
    if doc.status == "extracted":
        doc.status = "analyzed"
    db.flush()
    recompute_status(db, doc)
    db.commit()
    db.refresh(doc)
    return detail_to_out(doc)
