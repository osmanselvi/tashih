"""Musahhih (yazar) işaretlerini JSON dosyasına aktarma.

Dosya biçimi, masaüstü "Musahhih" uygulamasının okuyabildiği şemayla
uyumludur:

    {
      "pdfName": "kitap.pdf",
      "generatedAt": "...",
      "corrections": [ {id, type, oldText, newText, pageNum, x, y, rects, isCompleted} ],
      "aiSuggestions": [ ... aynı biçimde ... ]
    }

`corrections` yalnızca yazarın işaretlerini, `aiSuggestions` ise kural/LLM
önerilerini taşır; böylece dizgici dosyayı masaüstü uygulamada açtığında
yazar işaretleri PDF üzerinde kendi yerlerinde görünür.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

MUTATIONS = ("delete", "insert", "replace", "space", "join")


def _load_rect(value: str | None) -> list[float] | None:
    if not value:
        return None
    try:
        parsed = json.loads(value)
    except (TypeError, ValueError):
        return None
    if not isinstance(parsed, list) or len(parsed) < 4:
        return None
    return [float(v) for v in parsed[:4]]


def _rects(rect: list[float] | None) -> list[dict[str, float]]:
    """PDF puanlarındaki kutu → musahhih biçimi ({x, y, width, height})."""
    if not rect:
        return []
    x0, y0, x1, y1 = rect
    return [
        {
            "x": round(x0, 1),
            "y": round(y0, 1),
            "width": round(max(x1 - x0, 0.0), 1),
            "height": round(max(y1 - y0, 0.0), 1),
        }
    ]


def mutation_of(suggestion: Any) -> str:
    """Düzeltmenin türü: açık alan varsa o, yoksa metinden türetilir."""
    explicit = (getattr(suggestion, "mutation", None) or "").strip()
    if explicit in MUTATIONS:
        return explicit
    original = suggestion.original or ""
    replacement = suggestion.replacement or ""
    if original and not replacement:
        return "delete"
    if not original and replacement:
        return "insert"
    return "replace"


def correction_entry(suggestion: Any, page: Any) -> dict[str, Any]:
    """Tek bir işareti musahhih biçimindeki kayda çevirir."""
    rect = _load_rect(getattr(suggestion, "rect", None))
    rects = _rects(rect)
    return {
        "id": str(suggestion.id),
        "type": mutation_of(suggestion),
        "oldText": suggestion.original or "",
        "newText": suggestion.replacement or "",
        "pageNum": page.number,
        "x": rect[0] if rect else 0.0,
        "y": rect[1] if rect else 0.0,
        "rects": rects,
        "isCompleted": suggestion.status == "accepted",
        # ek bilgi (masaüstü uygulama yok sayar)
        "kind": suggestion.kind,
        "status": suggestion.status,
        "source": getattr(suggestion, "source", None) or "ai",
    }


def build_corrections_json(doc: Any) -> bytes:
    """Belgenin tüm düzeltmelerini iki alanlı JSON olarak üretir."""
    manual: list[dict[str, Any]] = []
    ai: list[dict[str, Any]] = []
    for page in doc.pages:
        for suggestion in page.suggestions:
            entry = correction_entry(suggestion, page)
            if (getattr(suggestion, "source", None) or "ai") == "manual":
                manual.append(entry)
            else:
                ai.append(entry)

    payload = {
        "pdfName": doc.filename,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "corrections": manual,
        "aiSuggestions": ai,
    }
    return json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
