"""Orijinal PDF sayfası üzerinde düzeltme noktalarını konumlandırma.

OCR kullanılmaz; yalnızca PDF'in metin katmanı okunur. Metin ve sözcük
kutuları AYNI rawdict geçişinden üretildiği için metin ofsetleri kutularla
birebir hizalıdır. Eski kayıtlar (hizasız metin) için PDF üzerinde metin
araması kullanılır.
"""
from __future__ import annotations

import re
from pathlib import Path

Rect = list[float]


def _union(boxes: list[Rect]) -> Rect:
    return [
        min(b[0] for b in boxes),
        min(b[1] for b in boxes),
        max(b[2] for b in boxes),
        max(b[3] for b in boxes),
    ]


def build_page_content(page) -> tuple[str, dict, float, float]:
    """Sayfadan (metin, geometri, genişlik, yükseklik) üretir.

    Dönüş geometrisi: {"aligned": True, "words": [{"start", "end", "rect"}]}
    - start/end: üretilen metindeki ofsetler (kelime karakterleri)
    - rect: [x0, y0, x1, y1] PDF puanları, sol üst orijin, y aşağı büyür
    """
    data = page.get_text("rawdict")
    text_blocks = [b for b in data.get("blocks", []) if b.get("type", 0) == 0]

    parts: list[str] = []
    words: list[dict] = []
    offset = 0

    word_chars: list[str] = []
    word_boxes: list[Rect] = []
    word_start = -1

    def flush_word() -> None:
        nonlocal word_chars, word_boxes, word_start
        if word_chars and word_boxes:
            words.append(
                {
                    "start": word_start,
                    "end": offset,
                    "rect": [round(v, 2) for v in _union(word_boxes)],
                }
            )
        word_chars = []
        word_boxes = []
        word_start = -1

    for block_index, block in enumerate(text_blocks):
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                for ch in span.get("chars", []):
                    c = ch.get("c") or ""
                    if not c:
                        continue
                    if c in ("\n", "\r"):
                        flush_word()
                        parts.append("\n")
                        offset += 1
                        continue
                    if c.isspace() or c == "\u00a0":
                        flush_word()
                        parts.append(" ")
                        offset += 1
                        continue
                    if not word_chars:
                        word_start = offset
                    word_chars.append(c)
                    box = ch.get("bbox")
                    if box:
                        word_boxes.append(list(box))
                    parts.append(c)
                    offset += 1
            flush_word()
            parts.append("\n")
            offset += 1
        if block_index < len(text_blocks) - 1:
            parts.append("\n")  # bloklar arası paragraf ayracı
            offset += 1

    text = "".join(parts)
    geom = {"aligned": True, "words": words}
    rect = page.rect
    return text, geom, float(rect.width), float(rect.height)


def rect_from_words(geom: dict | None, start: int, end: int) -> Rect | None:
    """Metin ofsetlerinden [start, end) aralığının sayfa üstündeki kutusu."""
    if not geom or not geom.get("aligned"):
        return None
    words = geom.get("words") or []
    if not words or start < 0 or end < start:
        return None

    if start < end:
        hits = [w for w in words if w["start"] < end and w["end"] > start]
    else:  # sıfır genişlikli ekleme: sınırı içeren sözcükler
        hits = [w for w in words if w["start"] <= start <= w["end"]]

    if not hits:
        # Boşluk/tabana özel öneriler: komşu sözcüklerle çapa kur
        prev = [w for w in words if w["end"] <= start]
        nxt = [w for w in words if w["start"] >= (end if end > start else start)]
        if prev and nxt:
            hits = [prev[-1], nxt[0]]
        elif prev:
            hits = [prev[-1]]
        elif nxt:
            hits = [nxt[0]]
    if not hits:
        return None

    rect = _union([w["rect"] for w in hits])
    return [round(v, 1) for v in rect]


def shift_words(
    geom: dict | None,
    start: int,
    end: int,
    replacement: str,
    old_text: str,
) -> dict | None:
    """Metin değişikliğinden sonra sözcük ofsetlerini yeni metne hizalar.

    [start, end) aralığı `replacement` ile değiştirilmiştir. Sözcüklerin
    çekirdeği (kelime) esas alınır: kalan kısımlar yeni metindeki yerine
    eşlenir, tamamen silinen sözcükler listeden çıkar.
    """
    if not geom:
        return None
    words = geom.get("words")
    if not words:
        return geom

    delta = len(replacement) - (end - start)
    updated: list[dict] = []
    for word in words:
        w_start = int(word["start"])
        w_end = int(word["end"])
        if w_start >= end:
            updated.append({**word, "start": w_start + delta, "end": w_end + delta})
            continue
        if w_end <= start:
            updated.append(word)  # değişiklikten önce: yerinde kalır
            continue

        # Çakışan sözcük: çekirdek (kelime) kısmı esas alınır
        raw = (
            old_text[w_start:w_end]
            if 0 <= w_start <= w_end <= len(old_text)
            else ""
        )
        core = raw.strip()
        if not core:
            continue
        core_start = w_start + raw.index(core)
        core_end = core_start + len(core)

        if core_start >= start and core_end <= end:
            # Sözcük tamamen düzenleme bölgesinde
            if replacement.strip():
                updated.append(
                    {**word, "start": start, "end": start + len(replacement)}
                )
            continue

        segments: list[tuple[int, int]] = []
        if core_start < start:  # bölgeden önce kalan kısım
            segments.append((core_start, min(core_end, start)))
        if core_end > end:  # bölgeden sonra kalan kısım
            segments.append((max(core_start, end) + delta, core_end + delta))
        if replacement and start < core_end and core_start < end:
            segments.append((start, start + len(replacement)))
        if not segments:
            continue
        updated.append(
            {
                **word,
                "start": min(s[0] for s in segments),
                "end": max(s[1] for s in segments),
            }
        )

    geom["words"] = updated
    return geom


def word_at_point(geom: dict | None, x: float, y: float, text: str) -> dict | None:
    """Noktaya düşen sözcüğü bulur.

    Dönüş: {"start", "end", "text", "rect"} — rect PDF puanları (sol üst
    orijin). Tıklama harflerin arasına denk gelirse en yakın sözcük seçilir.
    """
    if not geom or not geom.get("aligned"):
        return None
    words = geom.get("words") or []
    if not words:
        return None

    hit: dict | None = None
    best: tuple[float, dict] | None = None
    for word in words:
        x0, y0, x1, y1 = word["rect"]
        if x0 <= x <= x1 and y0 <= y <= y1:
            hit = word
            break
        dx = max(x0 - x, 0.0, x - x1)
        dy = max(y0 - y, 0.0, y - y1)
        distance = (dx * dx + dy * dy) ** 0.5
        if distance <= 4.0 and (best is None or distance < best[0]):
            best = (distance, word)
    if hit is None:
        if best is None:
            return None
        hit = best[1]

    start, end = int(hit["start"]), int(hit["end"])
    if not (0 <= start <= end <= len(text)):
        return None

    # Sözcük kutusu bazen sondaki boşluğu da içerir; çekirdek (kelime) seçilir
    core = text[start:end]
    lead = len(core) - len(core.lstrip())
    trail = len(core) - len(core.rstrip())
    start += lead
    end -= trail
    if start >= end:
        return None

    return {
        "start": start,
        "end": end,
        "text": text[start:end],
        "rect": [round(float(v), 1) for v in hit["rect"]],
    }


def _context_word(text: str, start: int, end: int) -> str | None:
    """Boşluk temelli öneriler için çapa kelime: konumun önündeki/sonraki sözcük."""
    before = re.findall(r"\S+", text[:start])
    if before:
        return before[-1]
    after = re.findall(r"\S+", text[end:])
    if after:
        return after[0]
    return None


class PdfLocator:
    """PDF'i tek seferlik açar; metin katmanında arama yapar (OCR yok)."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self._doc = None
        self._opened = False

    def _open(self):
        if self._opened:
            return self._doc
        self._opened = True
        try:
            import pymupdf

            if self.path.is_file():
                self._doc = pymupdf.open(self.path)
        except Exception:
            self._doc = None
        return self._doc

    def close(self) -> None:
        if self._doc is not None:
            try:
                self._doc.close()
            except Exception:
                pass
            self._doc = None

    def __enter__(self) -> "PdfLocator":
        self._open()
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def page_size(self, page_number: int) -> tuple[float, float] | None:
        doc = self._open()
        if doc is None or not (0 <= page_number - 1 < doc.page_count):
            return None
        rect = doc[page_number - 1].rect
        return float(rect.width), float(rect.height)

    def page_content(self, page_number: int) -> tuple[str, dict, float, float] | None:
        """Sayfayı rawdict üzerinden yeniden ayrıştırır (eski kayıtları onarmak için)."""
        doc = self._open()
        if doc is None or not (0 <= page_number - 1 < doc.page_count):
            return None
        try:
            return build_page_content(doc[page_number - 1])
        except Exception:
            return None

    def search(
        self, page_number: int, text: str, original: str, start: int, end: int
    ) -> Rect | None:
        """Önerinin özgün metnini (veya çapa kelimesini) metin katmanında arar."""
        doc = self._open()
        if doc is None or not (0 <= page_number - 1 < doc.page_count):
            return None
        page = doc[page_number - 1]

        # Çok satırlı özgünlerde ilk satırı ara (arama satır aşamaz)
        needle = original.split("\n", 1)[0] if "\n" in original else original

        try:
            rects = []
            if needle.strip():
                rects = page.search_for(needle)
            if not rects:
                needle = _context_word(text, start, end) or ""
                if needle:
                    rects = page.search_for(needle)
        except Exception:
            return None
        if not rects:
            return None

        # Metin katmanındaki sırala: okuma sırası (y, x)
        rects = sorted(rects, key=lambda r: (round(r.y0, 1), r.x0))
        try:
            positions = [m.start() for m in re.finditer(re.escape(needle), text)]
        except re.error:
            positions = []
        if positions:
            # Hangi geçiş: metindeki konuma en yakın olan
            k = min(range(len(positions)), key=lambda i: abs(positions[i] - start))
            chosen = rects[min(k, len(rects) - 1)]
        else:
            chosen = rects[0]
        return [
            round(chosen.x0, 1),
            round(chosen.y0, 1),
            round(chosen.x1, 1),
            round(chosen.y1, 1),
        ]


    def word_at(self, page_number: int, x: float, y: float, text: str) -> dict | None:
        """PDF metin katmanında noktaya düşen sözcüğü bulur (yedek yol).

        Geometri hizasız eski kayıtlarda kullanılır; ofsetler sayfa metninde
        arama ile bulunur.
        """
        doc = self._open()
        if doc is None or not (0 <= page_number - 1 < doc.page_count):
            return None
        page = doc[page_number - 1]
        try:
            words = page.get_text("words")
        except Exception:
            return None

        best: tuple[float, float, float, float, str] | None = None
        best_distance: float | None = None
        for entry in words:
            wx0, wy0, wx1, wy1 = float(entry[0]), float(entry[1]), float(entry[2]), float(entry[3])
            wtext = (entry[4] or "").strip()
            if not wtext:
                continue
            if wx0 <= x <= wx1 and wy0 <= y <= wy1:
                best = (wx0, wy0, wx1, wy1, wtext)
                break
            dx = max(wx0 - x, 0.0, x - wx1)
            dy = max(wy0 - y, 0.0, y - wy1)
            distance = (dx * dx + dy * dy) ** 0.5
            if distance <= 4.0 and (best_distance is None or distance < best_distance):
                best_distance = distance
                best = (wx0, wy0, wx1, wy1, wtext)
        if best is None:
            return None

        wx0, wy0, wx1, wy1, wtext = best
        start = text.find(wtext)
        if start < 0:
            found = re.search(re.escape(wtext), text, re.IGNORECASE)
            start = found.start() if found else -1
        if start < 0:
            return None
        return {
            "start": start,
            "end": start + len(wtext),
            "text": text[start : start + len(wtext)],
            "rect": [round(wx0, 1), round(wy0, 1), round(wx1, 1), round(wy1, 1)],
        }


def resolve_rect(
    locator: PdfLocator | None,
    geom: dict | None,
    page_number: int,
    text: str,
    start: int,
    end: int,
    original: str,
) -> Rect | None:
    """Öneri için sayfa üstünde bir dikdörtgen bulur (önce hizalı geometri)."""
    rect = rect_from_words(geom, start, end)
    if rect is not None:
        return rect
    if locator is not None:
        return locator.search(page_number, text, original, start, end)
    return None
