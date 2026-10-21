"""Uçtan uca API testi: yükle → analiz → kabul/geri al/red → düzenle → dışa aktar → sil."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app

TEST_LINES = [
    "Tashih Duzeltme Denemesi",
    "",
    "Bu cumle  fazla bosluk icerir.",
    "Ikinci cumle tekrar tekrar ayni kelimeyi yazar.",
    "Merhaba , dunya! Naber ?",
]


def _make_pdf_bytes() -> bytes:
    import pymupdf

    doc = pymupdf.open()
    page = doc.new_page()
    y = 72
    for line in TEST_LINES:
        page.insert_text((72, y), line, fontsize=12)
        y += 18
    data = doc.tobytes()
    doc.close()
    return data


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as test_client:
        yield test_client


def test_health(client: TestClient):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_full_workflow(client: TestClient):
    # --- yükleme ---
    r = client.post(
        "/api/documents",
        files={"file": ("ornek.pdf", _make_pdf_bytes(), "application/pdf")},
    )
    assert r.status_code == 200, r.text
    doc = r.json()
    doc_id = doc["id"]
    assert doc["page_count"] == 1
    assert doc["status"] == "extracted"

    # PDF olmayan dosya reddedilir
    r = client.post(
        "/api/documents", files={"file": ("ornek.txt", b"merhaba", "text/plain")}
    )
    assert r.status_code == 400

    # --- analiz (API anahtarı yok → heuristic) ---
    r = client.post(f"/api/documents/{doc_id}/analyze", json={})
    assert r.status_code == 200, r.text
    detail = r.json()
    assert detail["analyzer_mode"] == "heuristic"
    assert detail["status"] == "analyzed"
    suggestions = detail["pages"][0]["suggestions"]
    assert suggestions, "kural tabanlı analiz en az bir öneri bulmalı"
    assert detail["pending_count"] == len(suggestions)
    original_text = detail["pages"][0]["text"]

    # --- baloncuk geometrisi: sayfa ölçüleri + her önerinin konumu ---
    page_out = detail["pages"][0]
    assert page_out["width"] and page_out["height"]
    for s in suggestions:
        assert s["rect"] is not None, f"konum bulunamadı: {s}"
        x0, y0, x1, y1 = s["rect"]
        assert 0 <= x0 <= x1 <= page_out["width"] + 1
        assert 0 <= y0 <= y1 <= page_out["height"] + 1

    target = next(s for s in suggestions if s["original"])

    # --- kabul ---
    r = client.patch(
        f"/api/suggestions/{target['id']}", json={"status": "accepted"}
    )
    assert r.status_code == 200, r.text
    result = r.json()
    assert result["suggestion"]["status"] == "accepted"
    new_text = result["page"]["text"]
    assert new_text != original_text
    # Kalan önerilerin ofsetleri metinle tutarlı kalmalı
    for s in result["page"]["suggestions"]:
        if s["status"] == "pending":
            assert new_text[s["start"] : s["end"]] == s["original"]

    # --- geri al ---
    r = client.patch(f"/api/suggestions/{target['id']}", json={"status": "pending"})
    assert r.status_code == 200, r.text
    assert r.json()["page"]["text"] == original_text

    # --- reddet ---
    r = client.patch(
        f"/api/suggestions/{target['id']}", json={"status": "rejected"}
    )
    assert r.status_code == 200
    assert r.json()["suggestion"]["status"] == "rejected"

    # --- elle düzenleme: bekleyen öneriler kalkar, günlük tutulur ---
    edited = original_text + "\nYeni eklenen satir."
    r = client.put(
        f"/api/documents/{doc_id}/pages/1", json={"text": edited}
    )
    assert r.status_code == 200, r.text
    page_out = r.json()
    assert page_out["text"] == edited
    assert not [s for s in page_out["suggestions"] if s["status"] == "pending"]

    r = client.get(f"/api/documents/{doc_id}/changelog")
    assert r.status_code == 200
    entries = r.json()
    assert len(entries) >= 2
    assert {"id", "page_number", "old_text", "new_text", "source", "created_at"} <= set(entries[0])

    # --- sayfa görüntüsü ---
    r = client.get(f"/api/documents/{doc_id}/pages/1/image")
    assert r.status_code == 200
    assert r.content[:8] == b"\x89PNG\r\n\x1a\n"

    # --- dışa aktarma ---
    r = client.post(f"/api/documents/{doc_id}/export", json={"format": "txt"})
    assert r.status_code == 200 and r.content
    assert "attachment" in r.headers["content-disposition"]

    r = client.post(f"/api/documents/{doc_id}/export", json={"format": "md"})
    assert r.status_code == 200 and b"Sayfa 1" in r.content

    r = client.post(f"/api/documents/{doc_id}/export", json={"format": "docx"})
    assert r.status_code == 200 and r.content[:2] == b"PK"

    # --- durum: reviewing ---
    r = client.get(f"/api/documents/{doc_id}")
    assert r.status_code == 200
    assert r.json()["status"] == "reviewing"

    # --- 404'ler ---
    assert client.get("/api/documents/999999").status_code == 404
    assert client.get(f"/api/documents/{doc_id}/pages/42/image").status_code == 404

    # --- silme ---
    r = client.delete(f"/api/documents/{doc_id}")
    assert r.status_code == 200 and r.json()["ok"] is True
    assert client.get(f"/api/documents/{doc_id}").status_code == 404


def test_backfill_geometry(client: TestClient):
    """Eski kayıtlarda eksik sayfa ölçüleri ve konumlar açılışta tamamlanır."""
    from sqlalchemy import select

    from app.db import SessionLocal
    from app.models import Document, Suggestion
    from app.services.backfill import backfill_geometry

    r = client.post(
        "/api/documents",
        files={"file": ("geriye-donus.pdf", _make_pdf_bytes(), "application/pdf")},
    )
    assert r.status_code == 200, r.text
    doc_id = r.json()["id"]
    r = client.post(f"/api/documents/{doc_id}/analyze", json={})
    assert r.status_code == 200, r.text
    assert r.json()["pages"][0]["suggestions"]

    # Alanları bilerek sil (yüklememiş eski kayıtları taklit et)
    db = SessionLocal()
    doc = db.get(Document, doc_id)
    for page in doc.pages:
        page.width = None
        page.height = None
        page.words = None
    for sug in db.scalars(select(Suggestion).where(Suggestion.document_id == doc_id)):
        sug.rect = None
    db.commit()
    db.close()

    backfill_geometry()

    detail = client.get(f"/api/documents/{doc_id}").json()
    page = detail["pages"][0]
    assert page["width"] and page["height"]
    assert page["suggestions"]
    assert all(s["rect"] for s in page["suggestions"])

    client.delete(f"/api/documents/{doc_id}")


def test_backfill_runs_once(client: TestClient, monkeypatch):
    """Eski kayıtlarda backfill her açılışta aynı işi tekrarlamaz."""
    from app.db import SessionLocal
    from app.models import Document
    from app.services.backfill import backfill_geometry
    from app.services.geometry import PdfLocator

    calls = {"n": 0}
    original_page_content = PdfLocator.page_content

    def counting_page_content(self, page_number: int):
        calls["n"] += 1
        return original_page_content(self, page_number)

    monkeypatch.setattr(PdfLocator, "page_content", counting_page_content)

    r = client.post(
        "/api/documents",
        files={"file": ("tek-sefer.pdf", _make_pdf_bytes(), "application/pdf")},
    )
    assert r.status_code == 200, r.text
    doc_id = r.json()["id"]
    r = client.post(f"/api/documents/{doc_id}/analyze", json={})
    assert r.status_code == 200, r.text
    assert r.json()["pages"][0]["suggestions"]

    # Eski kaydı taklit et: metin PDF'ten üretilenden farklı, geometri yok
    db = SessionLocal()
    doc = db.get(Document, doc_id)
    page = doc.pages[0]
    page.width = None
    page.height = None
    page.words = None
    page.text = page.text + "\nsonradan eklendi"
    sug = page.suggestions[0]
    sug.rect = None
    db.commit()

    backfill_geometry()
    db.refresh(page)
    db.refresh(sug)
    assert page.width and page.height
    assert page.words is None  # metin farklı → hizalanamadı, saklanmadı
    assert sug.rect  # arama yedeğiyle bulundu
    assert calls["n"] >= 1

    # rect'ler dolu: ikinci çalışma hiç geometri kurmaz (doc1'in durumu)
    calls["n"] = 0
    backfill_geometry()
    assert calls["n"] == 0
    db.refresh(page)
    assert page.words is None

    # Bulunamayan konum bir kez "[]" ile işaretlenir, sonra aranmaz
    page.text = "zzz"
    sug.original = "zzz"
    sug.start = 0
    sug.end = 3
    sug.rect = None
    db.commit()
    backfill_geometry()
    db.refresh(sug)
    assert sug.rect == "[]"
    calls["n"] = 0
    backfill_geometry()
    db.refresh(sug)
    assert calls["n"] == 0
    assert sug.rect == "[]"

    db.close()
    client.delete(f"/api/documents/{doc_id}")
