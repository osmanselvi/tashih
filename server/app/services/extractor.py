"""PDF dosyasından metin + geometri ve sayfa görüntüsü çıkarma."""
from __future__ import annotations

import json
from pathlib import Path

from .geometry import build_page_content

RENDER_ZOOM = 2.0  # sayfa görüntüsü çözünürlüğü (1.0 = 72dpi)


def extract_pdf(pdf_path: Path, image_dir: Path) -> list[dict]:
    """PDF'i sayfa sayfa ayrıştırır.

    Her sayfa için metin (metin katmanından, OCR yok), geometri (sözcük
    kutuları), sayfa ölçüleri ve PNG görüntüsü üretilir.
    """
    try:
        import pymupdf as fitz  # PyMuPDF
    except ImportError:
        try:
            import fitz  # noqa: F401  (eski sürüm takma adı)
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError(
                "PyMuPDF kurulu değil. 'pip install pymupdf' ile kurun."
            ) from exc

    image_dir.mkdir(parents=True, exist_ok=True)
    results: list[dict] = []
    matrix = fitz.Matrix(RENDER_ZOOM, RENDER_ZOOM)

    with fitz.open(pdf_path) as doc:
        for index, page in enumerate(doc, start=1):
            text, geom, width, height = build_page_content(page)
            pixmap = page.get_pixmap(matrix=matrix, alpha=False)
            pixmap.save(image_dir / f"page_{index}.png")
            results.append(
                {
                    "number": index,
                    "text": text,
                    "has_text": bool(text.strip()),
                    "width": width,
                    "height": height,
                    "words": json.dumps(geom),
                }
            )
    return results
