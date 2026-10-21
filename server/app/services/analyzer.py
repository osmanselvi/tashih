"""Öneri üretimi: LLM (OpenAI uyumlu) veya kural tabanlı yedek.

LLM_API_KEY tanımlıysa model çağrılır; model hata verirse veya anahtar
yoksa sessizce kural tabanlı analize düşülür.
"""
from __future__ import annotations

import json
import re

import httpx

from ..config import DEFAULT_LANG, LLM_API_KEY, LLM_BASE_URL, LLM_MODEL

MAX_SUGGESTIONS_PER_PAGE = 30
MAX_OCCURRENCES = 5
CHUNK_SIZE = 6000
VALID_KINDS = {"spelling", "grammar", "punctuation", "ocr", "style"}

# ---------------------------------------------------------------------------
# Açıklamalar (tr / en)
# ---------------------------------------------------------------------------
_EXPLANATIONS: dict[str, tuple[str, str]] = {
    "double_space": (
        "Ardışık fazla boşluk tek boşlukla değiştirilmeli.",
        "Consecutive extra spaces should be a single space.",
    ),
    "space_before_punct": (
        "Noktalama işaretinden önce boşluk bulunmamalı.",
        "There should be no space before punctuation marks.",
    ),
    "missing_space": (
        "Noktalama işaretinden sonra boşluk eksik.",
        "A space is missing after the punctuation mark.",
    ),
    "repeated_word": (
        "Kelime gereksiz yinelenmiş.",
        "The word is repeated unnecessarily.",
    ),
    "dup_punct": (
        "Noktalama işareti tekrarlanmış.",
        "The punctuation mark is duplicated.",
    ),
}


def _explain(key: str) -> str:
    tr, en = _EXPLANATIONS.get(key, ("", ""))
    return tr if DEFAULT_LANG == "tr" else en


# ---------------------------------------------------------------------------
# Kural tabanlı (heuristic) analiz
# ---------------------------------------------------------------------------
_HEURISTIC_RULES: list[tuple[re.Pattern[str], object, str, str]] = [
    # (kalıp, değiştirme, kind, açıklama anahtarı)
    (re.compile(r"(?<=\S) {2,}(?=\S)"), lambda m: " ", "ocr", "double_space"),
    (
        re.compile(r"(?<=\S) +(?=[,.;:!?])"),
        lambda m: "",
        "punctuation",
        "space_before_punct",
    ),
    (
        re.compile(r"\b(\w{2,})\s+\1\b", re.IGNORECASE),
        lambda m: m.group(1),
        "grammar",
        "repeated_word",
    ),
    (re.compile(r"([,;:!?])\1+"), lambda m: m.group(1), "punctuation", "dup_punct"),
    (
        re.compile(r"(?<=[,;:!?])(?=[A-Za-zÇĞİÖŞÜçğıöşü])"),
        lambda m: " ",
        "punctuation",
        "missing_space",
    ),
]

# Üç nokta: "..." ya da PDF metin katmanında "boşluklu" hâlde çıkan ". . ."
_ELLIPSIS_RE = re.compile(r"\.(\s*\.){2,}")
_ELLIPSIS_MASK = "\x00"


def _mask_ellipsis(text: str) -> str:
    """Üç noktalı dizileri maskeler.

    PDF metin katmanında noktalar arasında yapay boşluklar çıkabiliyor
    ("çünkü . . ."). Bunları "noktalama öncesi boşluk" hatası saymak yanlış
    olurdu; üç nokta cümle sonunda zaten boşlukla kullanılır.

    Maskeleme ofsetleri korur: her karakter tek tek değiştirilir.
    """
    if "." not in text:
        return text
    chars = list(text)
    for match in _ELLIPSIS_RE.finditer(text):
        for index in range(match.start(), match.end()):
            chars[index] = _ELLIPSIS_MASK
    return "".join(chars)


def _heuristic(text: str) -> list[dict]:
    drafts: list[dict] = []
    masked = _mask_ellipsis(text)
    for pattern, replacer, kind, key in _HEURISTIC_RULES:
        for match in pattern.finditer(masked):
            start, end = match.span()
            replacement = replacer(match)
            original = text[start:end]
            if replacement == original:
                continue
            drafts.append(
                {
                    "start": start,
                    "end": end,
                    "original": original,
                    "replacement": replacement,
                    "kind": kind,
                    "explanation": _explain(key),
                }
            )
    return drafts


# ---------------------------------------------------------------------------
# LLM analizi
# ---------------------------------------------------------------------------
_SYSTEM_PROMPT = """Sen kıdemli bir metin musahhihisin (sen deneyimli bir proofreadersin).
Sana verilen metindeki yazım, imla, noktalama, OCR ve tutarlılık hatalarını bul.

Yalnızca kesin hataları bildir; anlamı değiştiren veya üslup tercihine dayanan önerilerde bulunma.

SADECE şu şemada bir JSON nesnesi döndür, başka hiçbir şey yazma:
{"suggestions": [{"original": "<metindeki tam dizey>", "replacement": "<düzeltme, silinecekse boş>", "kind": "<spelling|grammar|punctuation|ocr|style>", "explanation": "<kısa açıklama>"}]}

Kurallar:
- "original" metinde BİREBİR (büyük/küçük harf dahil) bulunmalıdır.
- Tekrarlanan boşluk/noktalama gibi yerel hatalar için orijinal dizgeyi tam metinden al.
- En fazla 20 öneri; aynı hatayı iki kez bildirme.
- Açıklamayı metnin diliyle yaz."""


def _parse_json_object(content: str) -> dict | None:
    content = content.strip()
    if content.startswith("```"):
        content = re.sub(r"^```[a-zA-Z]*\s*", "", content)
        content = re.sub(r"\s*```$", "", content)
    try:
        obj = json.loads(content)
        return obj if isinstance(obj, dict) else None
    except json.JSONDecodeError:
        pass
    # İlk { den itibaren decode etmeyi dene
    start = content.find("{")
    if start == -1:
        return None
    try:
        obj, _ = json.JSONDecoder().raw_decode(content[start:])
        return obj if isinstance(obj, dict) else None
    except json.JSONDecodeError:
        return None


def _chat(messages: list[dict]) -> str:
    url = f"{LLM_BASE_URL}/chat/completions"
    headers = {"Authorization": f"Bearer {LLM_API_KEY}"}
    payload = {
        "model": LLM_MODEL,
        "temperature": 0,
        "messages": messages,
    }
    response = httpx.post(url, json=payload, headers=headers, timeout=90.0)
    response.raise_for_status()
    data = response.json()
    return data["choices"][0]["message"]["content"] or ""


def _locate(text: str, original: str) -> list[tuple[int, int]]:
    """original dizesinin text içindeki tüm geçişlerini döndürür."""
    if not original:
        return []
    spans = [m.span() for m in re.finditer(re.escape(original), text)]
    return spans[:MAX_OCCURRENCES]


def _llm_chunk(chunk: str) -> list[dict]:
    content = _chat(
        [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": chunk},
        ]
    )
    obj = _parse_json_object(content)
    if not obj:
        return []
    items = obj.get("suggestions")
    if not isinstance(items, list):
        return []

    drafts: list[dict] = []
    for item in items[:MAX_SUGGESTIONS_PER_PAGE]:
        if not isinstance(item, dict):
            continue
        original = str(item.get("original", ""))
        replacement = str(item.get("replacement", ""))
        kind = str(item.get("kind", "spelling"))
        if kind not in VALID_KINDS:
            kind = "spelling"
        explanation = str(item.get("explanation", "")).strip()
        for start, end in _locate(chunk, original):
            drafts.append(
                {
                    "start": start,
                    "end": end,
                    "original": original,
                    "replacement": replacement,
                    "kind": kind,
                    "explanation": explanation,
                }
            )
    return drafts


def _split_chunks(text: str) -> list[tuple[int, str]]:
    """Metni (başlangıç_ofseti, parça) listesine böler."""
    if len(text) <= CHUNK_SIZE:
        return [(0, text)]

    chunks: list[tuple[int, str]] = []
    cursor = 0
    while cursor < len(text):
        end = min(cursor + CHUNK_SIZE, len(text))
        if end < len(text):
            # Paragraf/kelime sınırına kadar geri çekil
            window = text[cursor:end]
            cut = max(window.rfind("\n\n"), window.rfind("\n"), window.rfind(" "))
            if cut > CHUNK_SIZE // 2:
                end = cursor + cut
        chunks.append((cursor, text[cursor:end]))
        cursor = end
    return chunks


def _llm_analyze(text: str) -> list[dict]:
    drafts: list[dict] = []
    for offset, chunk in _split_chunks(text):
        for draft in _llm_chunk(chunk):
            draft["start"] += offset
            draft["end"] += offset
            drafts.append(draft)
    return drafts


# ---------------------------------------------------------------------------
# Doğrulama ve dışa açılan ana fonksiyon
# ---------------------------------------------------------------------------
def _near_ellipsis(text: str, start: int, end: int) -> bool:
    """Düzeltme üç noktanın içinde ya da hemen yanında mı?

    Üç noktadan önceki/sonraki boşluğu "noktalama öncesi boşluk" diye
    bildirmek yanlıştır: noktalar arasındaki boşluk çoğunlukla PDF metin
    katmanının yapay ayrımıdır, cümle sonundaki "..." ise zaten boşlukla
    yazılır.
    """
    for match in _ELLIPSIS_RE.finditer(text):
        if match.start() <= end and start <= match.end():
            return True
    return False


def _finalize(drafts: list[dict], text: str) -> list[dict]:
    valid: list[dict] = []
    for draft in drafts:
        start, end = int(draft["start"]), int(draft["end"])
        original = str(draft["original"])
        if not (0 <= start <= end <= len(text)):
            continue
        if text[start:end] != original:
            continue
        if start == end and not draft["replacement"]:
            continue  # boş değişiklik yok
        if not original.strip() and _near_ellipsis(text, start, end):
            continue  # üç noktaya ait yapay boşluk
        valid.append({**draft, "start": start, "end": end})

    # Başlangıca göre sırala, çakışan önerileri ele (ilkini koru)
    valid.sort(key=lambda d: (d["start"], -(d["end"] - d["start"])))
    result: list[dict] = []
    last_end = -1
    for draft in valid:
        if draft["start"] < last_end:
            continue
        result.append(draft)
        last_end = draft["end"]
        if len(result) >= MAX_SUGGESTIONS_PER_PAGE:
            break
    return result


def analyze_page(text: str) -> tuple[list[dict], str]:
    """Sayfa metnini analiz eder.

    Dönüş: (öneri_listesi, mod) — mod: "llm" | "heuristic"
    """
    mode = "llm" if LLM_API_KEY else "heuristic"
    if not text.strip():
        return [], mode
    if LLM_API_KEY:
        try:
            return _finalize(_llm_analyze(text), text), "llm"
        except Exception:
            # LLM hatası → kural tabanlı analize düş
            return _finalize(_heuristic(text), text), "heuristic"
    return _finalize(_heuristic(text), text), "heuristic"
