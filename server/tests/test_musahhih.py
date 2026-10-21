"""Musahhih (yazar) işareti testleri: tıklama → kelime → düzeltme → JSON."""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from app.main import app

TEST_LINES = [
    "Tashih musahhih testi.",
    "Bu cumle  fazla bosluk icerir.",
    "Metin devam ediyor ...",
    "Baska cumle . . . devam ediyor.",
]


def _make_pdf_bytes(lines: list[str] | None = None) -> bytes:
    import pymupdf

    doc = pymupdf.open()
    page = doc.new_page()
    y = 72
    for line in lines or TEST_LINES:
        page.insert_text((72, y), line, fontsize=12)
        y += 18
    data = doc.tobytes()
    doc.close()
    return data


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as test_client:
        yield test_client


def _upload(client: TestClient, filename: str = "musahhih-ornek.pdf"):
    r = client.post(
        "/api/documents",
        files={"file": (filename, _make_pdf_bytes(), "application/pdf")},
    )
    assert r.status_code == 200, r.text
    return r.json()


def test_ellipsis_is_not_a_punctuation_error(client: TestClient):
    """Cümle sonundaki '...' ve boşluklu '. . .' hata sayılmamalı."""
    doc = _upload(client, "ucun-nokta.pdf")
    doc_id = doc["id"]

    r = client.post(f"/api/documents/{doc_id}/analyze", json={})
    assert r.status_code == 200, r.text
    page = r.json()["pages"][0]

    whitespace_suggestions = [
        s
        for s in page["suggestions"]
        if not s["original"].strip() and s["kind"] == "punctuation"
    ]
    assert whitespace_suggestions == [], "üç nokta yapay boşluk sayıldı"

    # Üç noktalı cümleler metinde olduğu gibi kalmalı
    assert "..." in page["text"]
    assert ". . ." in page["text"]

    # Gerçek hatalar (çift boşluk) yine bulunmalı
    assert any(s["kind"] == "ocr" for s in page["suggestions"])

    client.delete(f"/api/documents/{doc_id}")


def test_manual_correction_flow(client: TestClient):
    """Tıkla → kelime bul → düzeltme oluştur → JSON'a aktar → geri al."""
    doc = _upload(client)
    doc_id = doc["id"]
    page = doc["pages"][0]
    page_id = page["id"]
    original_text = page["text"]

    # --- tıklanan noktadaki kelime bulunur ---
    from app.db import SessionLocal
    from app.models import Document

    db = SessionLocal()
    stored = db.get(Document, doc_id)
    geom = json.loads(stored.pages[0].words)
    word = geom["words"][0]
    db.close()
    x = (word["rect"][0] + word["rect"][2]) / 2
    y = (word["rect"][1] + word["rect"][3]) / 2

    r = client.post(
        f"/api/documents/{doc_id}/pages/1/word-at", json={"x": x, "y": y}
    )
    assert r.status_code == 200, r.text
    hit = r.json()
    assert hit["found"] is True
    assert hit["text"]
    assert hit["start"] < hit["end"]

    # --- silme işareti oluşturulur ---
    r = client.post(
        f"/api/documents/{doc_id}/corrections",
        json={
            "page_id": page_id,
            "start": hit["start"],
            "end": hit["end"],
            "mutation": "delete",
            "replacement": "",
        },
    )
    assert r.status_code == 200, r.text
    result = r.json()
    suggestion = result["suggestion"]
    assert suggestion["source"] == "manual"
    assert suggestion["mutation"] == "delete"
    assert suggestion["kind"] == "manual"
    assert suggestion["status"] == "accepted"
    assert suggestion["rect"], "işaretin sayfa üzerindeki konumu bulunamadı"

    # Düzeltme metne uygulanmış olmalı
    new_text = result["page"]["text"]
    assert new_text != original_text
    assert hit["text"] not in new_text

    # --- JSON dışa aktarma ---
    r = client.get(f"/api/documents/{doc_id}/corrections.json")
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["pdfName"] == "musahhih-ornek.pdf"
    assert data["generatedAt"]
    assert len(data["corrections"]) == 1
    entry = data["corrections"][0]
    assert entry["type"] == "delete"
    # Silme işareti kelimeyi ve ardındaki boşluğu birlikte kaldırır
    assert entry["oldText"].strip() == hit["text"]
    assert entry["newText"] == ""
    assert entry["pageNum"] == 1
    assert entry["rects"], "PDF üzerinde gösterilecek kutu eksik"
    assert entry["rects"][0]["width"] > 0
    assert entry["isCompleted"] is True
    assert "aiSuggestions" in data

    # --- geri al ---
    r = client.patch(f"/api/suggestions/{suggestion['id']}", json={"status": "pending"})
    assert r.status_code == 200, r.text
    assert r.json()["page"]["text"] == original_text

    # --- sil ---
    r = client.delete(f"/api/suggestions/{suggestion['id']}")
    assert r.status_code == 200 and r.json()["ok"] is True
    r = client.get(f"/api/documents/{doc_id}/corrections.json")
    assert r.json()["corrections"] == []

    client.delete(f"/api/documents/{doc_id}")


def test_correction_mutations(client: TestClient):
    """Değiştir / ekle / boşluk / birleştir işaretleri."""
    doc = _upload(client, "islemler.pdf")
    doc_id = doc["id"]
    page = doc["pages"][0]
    page_id = page["id"]
    text = page["text"]

    # Değiştir
    start = text.index("Tashih")
    end = start + len("Tashih")
    r = client.post(
        f"/api/documents/{doc_id}/corrections",
        json={
            "page_id": page_id,
            "start": start,
            "end": end,
            "mutation": "replace",
            "replacement": "Tashihh",
        },
    )
    assert r.status_code == 200, r.text
    assert r.json()["suggestion"]["mutation"] == "replace"
    assert "Tashihh" in r.json()["page"]["text"]

    # Ekle (kelimenin başına) — ofsetler güncel metinden alınır
    text = r.json()["page"]["text"]
    start = text.index("Tashihh")
    r = client.post(
        f"/api/documents/{doc_id}/corrections",
        json={
            "page_id": page_id,
            "start": start,
            "end": start,
            "mutation": "insert",
            "replacement": "Sayın ",
        },
    )
    assert r.status_code == 200, r.text
    assert r.json()["suggestion"]["mutation"] == "insert"
    assert "Sayın " in r.json()["page"]["text"]

    # Boşluk ekle (kelimenin sonuna)
    text = r.json()["page"]["text"]
    end = text.index("Tashihh") + len("Tashihh")
    r = client.post(
        f"/api/documents/{doc_id}/corrections",
        json={
            "page_id": page_id,
            "start": end,
            "end": end,
            "mutation": "space",
            "replacement": "",
        },
    )
    assert r.status_code == 200, r.text
    assert r.json()["suggestion"]["mutation"] == "space"
    assert "Tashihh " in r.json()["page"]["text"]

    # Birleştir: "cumle" + "fazla" → aradaki boşluk kaldırılır
    joined = r.json()["page"]["text"]
    idx = joined.index("cumle")
    r = client.post(
        f"/api/documents/{doc_id}/corrections",
        json={
            "page_id": page_id,
            "start": idx,
            "end": idx + len("cumle"),
            "mutation": "join",
            "replacement": "",
        },
    )
    assert r.status_code == 200, r.text
    assert r.json()["suggestion"]["mutation"] == "join"
    assert "cumlefazla" in r.json()["page"]["text"]

    # JSON'da tüm işaretler görünür
    r = client.get(f"/api/documents/{doc_id}/corrections.json")
    data = r.json()
    assert len(data["corrections"]) == 4
    assert {c["type"] for c in data["corrections"]} == {
        "replace",
        "insert",
        "space",
        "join",
    }

    client.delete(f"/api/documents/{doc_id}")


def test_word_lookup_stays_aligned_after_correction(client: TestClient):
    """Düzeltmeden sonra tıklama→kelime eşleşmesi bozulmamalı."""
    doc = _upload(client, "hizalama.pdf")
    doc_id = doc["id"]
    page = doc["pages"][0]
    page_id = page["id"]

    from app.db import SessionLocal
    from app.models import Document

    db = SessionLocal()
    stored = db.get(Document, doc_id)
    geom = json.loads(stored.pages[0].words)
    db.close()
    words = geom["words"]
    first, second = words[0], words[1]
    text = page["text"]
    expected_first = text[first["start"] : first["end"]].strip()
    expected_second = text[second["start"] : second["end"]].strip()

    def word_at(word):
        x = (word["rect"][0] + word["rect"][2]) / 2
        y = (word["rect"][1] + word["rect"][3]) / 2
        return client.post(
            f"/api/documents/{doc_id}/pages/1/word-at", json={"x": x, "y": y}
        ).json()

    hit_first = word_at(first)
    assert hit_first["found"] is True
    assert hit_first["text"] == expected_first

    # İlk kelime silinir (metin kısalır)
    r = client.post(
        f"/api/documents/{doc_id}/corrections",
        json={
            "page_id": page_id,
            "start": hit_first["start"],
            "end": hit_first["end"],
            "mutation": "delete",
            "replacement": "",
        },
    )
    assert r.status_code == 200, r.text

    # Sonraki kelime hâlâ doğru metni göstermeli (ofsetler hizalı kalmalı)
    hit_second = word_at(second)
    assert hit_second["found"] is True
    assert hit_second["text"] == expected_second
    assert hit_second["start"] < hit_second["end"]

    client.delete(f"/api/documents/{doc_id}")


def test_word_lookup_after_join(client: TestClient):
    """Birleştirme sonrası da kelime tıklanabilir kalmalı."""
    doc = _upload(client, "birlestir.pdf")
    doc_id = doc["id"]
    page = doc["pages"][0]
    page_id = page["id"]

    from app.db import SessionLocal
    from app.models import Document

    db = SessionLocal()
    stored = db.get(Document, doc_id)
    geom = json.loads(stored.pages[0].words)
    db.close()
    words = geom["words"]
    first = words[0]
    text = page["text"]
    expected = text[first["start"] : first["end"]].strip()

    x = (first["rect"][0] + first["rect"][2]) / 2
    y = (first["rect"][1] + first["rect"][3]) / 2
    hit = client.post(
        f"/api/documents/{doc_id}/pages/1/word-at", json={"x": x, "y": y}
    ).json()
    assert hit["found"] is True

    r = client.post(
        f"/api/documents/{doc_id}/corrections",
        json={
            "page_id": page_id,
            "start": hit["start"],
            "end": hit["end"],
            "mutation": "join",
            "replacement": "",
        },
    )
    assert r.status_code == 200, r.text
    assert r.json()["suggestion"]["mutation"] == "join"

    # Kelime hâlâ bulunabilmeli (geometri bozulmamalı)
    hit2 = client.post(
        f"/api/documents/{doc_id}/pages/1/word-at", json={"x": x, "y": y}
    ).json()
    assert hit2["found"] is True
    assert hit2["text"] == expected

    client.delete(f"/api/documents/{doc_id}")


def test_mark_can_be_deleted_after_manual_text_edit(client: TestClient):
    """Metin elle değiştirilmiş olsa da işaret silinebilmeli (409 olmamalı)."""
    doc = _upload(client, "elle-duzenleme.pdf")
    doc_id = doc["id"]
    page = doc["pages"][0]
    page_id = page["id"]
    text = page["text"]

    start = text.index("Tashih")
    r = client.post(
        f"/api/documents/{doc_id}/corrections",
        json={
            "page_id": page_id,
            "start": start,
            "end": start + len("Tashih"),
            "mutation": "replace",
            "replacement": "Tashihh",
        },
    )
    assert r.status_code == 200, r.text
    suggestion = r.json()["suggestion"]

    # Yazar metni elle değiştirir (ofsetler eskir)
    new_text = r.json()["page"]["text"].replace("Tashihh", "Tas")
    r = client.put(f"/api/documents/{doc_id}/pages/1", json={"text": new_text})
    assert r.status_code == 200, r.text

    # İşaret yine de silinebilmeli
    r = client.delete(f"/api/suggestions/{suggestion['id']}")
    assert r.status_code == 200, r.text
    assert r.json()["ok"] is True

    r = client.get(f"/api/documents/{doc_id}/corrections.json")
    assert r.json()["corrections"] == []
    # Metne dokunulmadı (geri alınamadıysa da yazarın metni korunur)
    r = client.get(f"/api/documents/{doc_id}")
    assert r.json()["pages"][0]["text"] == new_text

    client.delete(f"/api/documents/{doc_id}")


def test_correction_validation(client: TestClient):
    doc = _upload(client, "gecersiz.pdf")
    doc_id = doc["id"]
    page_id = doc["pages"][0]["id"]

    # Sayfa dışı konum
    r = client.post(
        f"/api/documents/{doc_id}/corrections",
        json={
            "page_id": page_id,
            "start": 10_000,
            "end": 10_005,
            "mutation": "delete",
            "replacement": "",
        },
    )
    assert r.status_code == 400

    # Boş değiştirme
    r = client.post(
        f"/api/documents/{doc_id}/corrections",
        json={
            "page_id": page_id,
            "start": 0,
            "end": 3,
            "mutation": "replace",
            "replacement": "",
        },
    )
    assert r.status_code == 400

    # Var olmayan sayfa
    r = client.post(
        f"/api/documents/{doc_id}/corrections",
        json={
            "page_id": 999_999,
            "start": 0,
            "end": 3,
            "mutation": "delete",
            "replacement": "",
        },
    )
    assert r.status_code == 404

    client.delete(f"/api/documents/{doc_id}")
