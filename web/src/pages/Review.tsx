import {
  Fragment,
  useCallback,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
} from "react";
import { Link, useParams } from "react-router-dom";
import ChangeLogPanel from "../components/ChangeLogPanel";
import SuggestionCard from "../components/SuggestionCard";
import {
  ApiError,
  analyzeDocument,
  createCorrection,
  deleteSuggestion,
  errorMessage,
  exportCorrectionsJson,
  exportDocument,
  getDocument,
  isAbortError,
  pageImageUrl,
  patchSuggestion,
  putPageText,
  wordAtPoint,
} from "../api";
import {
  mutationKey,
  setLang,
  statusKey,
  t,
  translateError,
  useLang,
} from "../i18n";
import { mutationType } from "../types";
import type {
  CorrectionMutation,
  DocumentDetail,
  ExportFormat,
  MutationType,
  Page,
  Suggestion,
  SuggestionStatus,
  WordHit,
} from "../types";

const EXPORT_FORMATS: ExportFormat[] = ["txt", "md", "docx"];
const ZOOM_STEP = 0.25;
const ZOOM_MIN = 0.5;
const ZOOM_MAX = 3;

const BUBBLE_SYMBOLS: Record<MutationType, string> = {
  delete: "−",
  insert: "+",
  replace: "⇄",
  space: "␣",
  join: "><",
};

/** Baloncukta gösterge için kullanılan düzeltme türleri (sırayla gösterilir). */
const LEGEND_ORDER: MutationType[] = [
  "delete",
  "insert",
  "replace",
  "space",
  "join",
];

const BUBBLE_SIZE = 26; // baloncuk çapı (px)
const BUBBLE_INSET = 4; // görüntü kenarı ile baloncuk arası (px)
const BUBBLE_GAP = 6; // üst üste binmeyi engelleyen dikey boşluk (px)
const BUBBLE_STEP = BUBBLE_SIZE + BUBBLE_GAP;
/** Kesikli bağlantının sayfa kenarından başladığı uzaklık (px). */
const LEAD_OFFSET = BUBBLE_INSET + BUBBLE_SIZE + 4;

interface Bubble {
  suggestion: Suggestion;
  type: MutationType;
  /** [x0, y0, x1, y1] in PDF points. */
  rect: [number, number, number, number];
  side: "left" | "right";
}

/** Görüntü çerçevesinin piksel ölçüsü. */
interface FrameSize {
  w: number;
  h: number;
}

interface PlacedBubble extends Bubble {
  /** Baloncuk merkezinin çerçeve içindeki piksel konumu (dikey ortalı). */
  center: number;
  /** Kesikli bağlantı çizgisinin uçları (piksel). */
  line: { x1: number; y1: number; x2: number; y2: number };
  /** Düzeltme noktasının sayfa üstündeki vurgu kutusu (piksel). */
  box: { x: number; y: number; w: number; h: number };
}

/** Sayfa görselinde tıklanan noktada açılan işaretleme penceresi. */
interface MarkState {
  /** Tıklanan noktanın görsel içindeki piksel konumu. */
  px: number;
  py: number;
  /** Tıklanan noktadaki kelime (sunucu bulur). */
  hit: WordHit;
  /** Seçilen eylem; null ise eylem menüsü gösterilir. */
  action: CorrectionMutation | null;
  /** Değiştirme/ekleme için girilen metin. */
  value: string;
}

function clampRange(value: number, min: number, max: number): number {
  if (!Number.isFinite(value)) return min;
  return Math.min(max, Math.max(min, value));
}

/** Baloncuklar yalnızca konumu bilinen düzeltmeler için çizilir. */
function buildBubbles(page: Page): Bubble[] {
  const width = page.width;
  const height = page.height;
  if (width == null || height == null) return [];
  if (!Number.isFinite(width) || !Number.isFinite(height)) return [];
  if (width <= 0 || height <= 0) return [];

  const bubbles: Bubble[] = [];
  for (const suggestion of page.suggestions) {
    const manual = suggestion.source === "manual";
    if (manual) {
      // Yazar işaretleri kabul edilmiş olarak doğar; reddedilirse gizlenir
      if (suggestion.status === "rejected") continue;
    } else if (suggestion.status !== "pending") {
      continue;
    }
    const rect = suggestion.rect;
    if (rect == null) continue;
    const [x0, y0, x1, y1] = rect;
    if (![x0, y0, x1, y1].every(Number.isFinite)) continue;
    if (x1 <= x0 || y1 <= y0) continue;

    bubbles.push({
      suggestion,
      type: mutationType(suggestion),
      rect: [x0, y0, x1, y1],
      side: (x0 + x1) / 2 < width / 2 ? "left" : "right",
    });
  }
  return bubbles;
}

/**
 * Baloncukları piksel cinsinden sayfa üstüne yerleştirir:
 * - vurgu kutusu tam düzeltme noktasını örter,
 * - aynı hizada kalan baloncuklar üst üste gelmeyecek şekilde istiflenir,
 * - bağlantı çizgisi baloncuktan düzeltme noktasına uzanır.
 */
function placeBubbles(
  bubbles: Bubble[],
  size: FrameSize,
  pageWidth: number,
): PlacedBubble[] {
  if (size.w <= 0 || size.h <= 0 || pageWidth <= 0) return [];
  const scale = size.w / pageWidth;
  const radius = BUBBLE_SIZE / 2;
  const maxCenter = Math.max(radius, size.h - radius);

  const placed: PlacedBubble[] = bubbles.map((bubble) => {
    const [x0, y0, x1, y1] = bubble.rect;
    const box = {
      x: x0 * scale,
      y: y0 * scale,
      w: Math.max(2, (x1 - x0) * scale),
      h: Math.max(2, (y1 - y0) * scale),
    };
    return {
      ...bubble,
      box,
      center: clampRange(box.y + box.h / 2, radius, maxCenter),
      line: { x1: 0, y1: 0, x2: 0, y2: 0 },
    };
  });

  // Aynı hizada kalan baloncukları istifle (üst üste binmesinler)
  for (const side of ["left", "right"] as const) {
    const row = placed
      .filter((item) => item.side === side)
      .sort((a, b) => a.center - b.center);
    let next = -Infinity;
    for (const item of row) {
      item.center = Math.max(item.center, next);
      next = item.center + BUBBLE_STEP;
    }
    let limit = maxCenter;
    for (let i = row.length - 1; i >= 0; i -= 1) {
      row[i].center = Math.min(row[i].center, limit);
      if (i > 0) limit = row[i].center - BUBBLE_STEP;
    }
  }

  // Bağlantı: baloncğun iç kenarından düzeltme kutusunun sayfa kenarına
  for (const item of placed) {
    const rectCenterY = item.box.y + item.box.h / 2;
    if (item.side === "left") {
      item.line = {
        x1: LEAD_OFFSET,
        y1: item.center,
        x2: Math.max(item.box.x, LEAD_OFFSET),
        y2: rectCenterY,
      };
    } else {
      const edge = size.w - LEAD_OFFSET;
      item.line = {
        x1: edge,
        y1: item.center,
        x2: Math.min(item.box.x + item.box.w, edge),
        y2: rectCenterY,
      };
    }
  }
  return placed;
}

function bubbleTitle(bubble: Bubble): string {
  const original = bubble.suggestion.original || "∅";
  const replacement = bubble.suggestion.replacement || "∅";
  const prefix =
    bubble.suggestion.source === "manual" ? `${t("kindManual")} · ` : "";
  return `${prefix}${t(mutationKey(bubble.type))}: ${original} → ${replacement}`;
}

function pendingCountOnPage(page: DocumentDetail["pages"][number] | null): number {
  if (!page) return 0;
  return page.suggestions.filter((s) => s.status === "pending").length;
}

/** Belgedeki yazar (musahhih) işareti sayısı. */
function manualMarkCount(doc: DocumentDetail | null): number {
  if (!doc) return 0;
  return doc.pages.reduce(
    (total, page) =>
      total + page.suggestions.filter((s) => s.source === "manual").length,
    0,
  );
}

export default function Review() {
  const params = useParams();
  const lang = useLang();
  const id = Number(params.id);
  const idValid = Number.isInteger(id) && id > 0;

  const [doc, setDoc] = useState<DocumentDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [notFound, setNotFound] = useState(false);

  const [activeIndex, setActiveIndex] = useState(0);
  const [zoom, setZoom] = useState(1);
  const [imageFailed, setImageFailed] = useState(false);

  const [analyzing, setAnalyzing] = useState(false);
  const [exporting, setExporting] = useState<ExportFormat | null>(null);
  const [exportOpen, setExportOpen] = useState(false);
  const [changelogOpen, setChangelogOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [busySuggestionId, setBusySuggestionId] = useState<number | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [selectedSuggestionId, setSelectedSuggestionId] = useState<
    number | null
  >(null);

  // Musahhih (yazar) kontrolü
  const [musahhihMode, setMusahhihMode] = useState(false);
  const [mark, setMark] = useState<MarkState | null>(null);
  const [markBusy, setMarkBusy] = useState(false);
  const [exportingJson, setExportingJson] = useState(false);

  // Görüntü çerçevesinin piksel ölçüsü: vurgular ve baloncuklar buna göre çizilir
  const frameRef = useRef<HTMLDivElement>(null);
  const imageRef = useRef<HTMLImageElement>(null);
  const [frameSize, setFrameSize] = useState<FrameSize | null>(null);

  const load = useCallback(
    async (signal?: AbortSignal, silent = false): Promise<void> => {
      if (!idValid) {
        setLoading(false);
        setNotFound(true);
        return;
      }
      if (!silent) {
        setLoading(true);
        setLoadError(null);
        setNotFound(false);
      }
      try {
        const detail = await getDocument(id, signal);
        setDoc(detail);
        setActiveIndex((index) =>
          Math.min(index, Math.max(0, detail.pages.length - 1)),
        );
      } catch (err: unknown) {
        if (isAbortError(err)) return;
        if (err instanceof ApiError && err.status === 404) {
          setNotFound(true);
        } else {
          setLoadError(translateError(errorMessage(err)));
        }
      } finally {
        if (!signal?.aborted) setLoading(false);
      }
    },
    [id, idValid],
  );

  useEffect(() => {
    const controller = new AbortController();
    void load(controller.signal);
    return () => controller.abort();
  }, [load]);

  const page = doc && doc.pages.length > 0 ? doc.pages[activeIndex] : null;
  const pagePending = pendingCountOnPage(page);
  const manualMarks = manualMarkCount(doc);
  const canAnalyze = !!doc && doc.pages.some((p) => p.has_text);
  const allPagesTextless =
    !!doc && doc.pages.length > 0 && doc.pages.every((p) => !p.has_text);
  const imageSrc =
    doc && page ? pageImageUrl(doc.id, page.number) : null;

  useEffect(() => {
    setImageFailed(false);
  }, [imageSrc]);

  useEffect(() => {
    setSelectedSuggestionId(null);
    setMark(null);
  }, [page?.id]);

  // Musahhih modunda Esc işaretleme penceresini kapatır
  useEffect(() => {
    if (!mark) return;
    const onKey = (event: KeyboardEvent): void => {
      if (event.key === "Escape") setMark(null);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [mark]);

  // Çerçeve ölçüsünü izle: zoom, sayfa değişimi ve görsel yüklemesi değişince
  // yeniden hesaplanır (ResizeObserver).
  useLayoutEffect(() => {
    const el = frameRef.current;
    if (!el) {
      setFrameSize(null);
      return;
    }
    const measure = () => {
      const w = Math.round(el.clientWidth);
      const h = Math.round(el.clientHeight);
      setFrameSize((prev) =>
        prev && prev.w === w && prev.h === h ? prev : { w, h },
      );
    };
    measure();
    if (typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(measure);
    observer.observe(el);
    return () => observer.disconnect();
  }, [imageSrc, imageFailed, zoom]);

  const bubbles = page ? buildBubbles(page) : [];
  const placed: PlacedBubble[] =
    page && frameSize && page.width != null
      ? placeBubbles(bubbles, frameSize, page.width)
      : [];

  const selectSuggestion = (suggestionId: number): void => {
    setSelectedSuggestionId(suggestionId);
    const card = document.getElementById(`suggestion-${suggestionId}`);
    card?.scrollIntoView({ block: "center", behavior: "smooth" });
  };

  const replacePage = (updated: DocumentDetail["pages"][number]): void => {
    setDoc((current) => {
      if (!current) return current;
      return {
        ...current,
        pages: current.pages.map((p) => (p.id === updated.id ? updated : p)),
      };
    });
  };

  const handleTextChange = (value: string): void => {
    setDoc((current) => {
      if (!current) return current;
      return {
        ...current,
        pages: current.pages.map((p, index) =>
          index === activeIndex ? { ...p, text: value } : p,
        ),
      };
    });
  };

  const handleAnalyze = async (): Promise<void> => {
    if (!doc) return;
    setAnalyzing(true);
    setActionError(null);
    try {
      const updated = await analyzeDocument(doc.id);
      setDoc(updated);
      setActiveIndex((index) =>
        Math.min(index, Math.max(0, updated.pages.length - 1)),
      );
    } catch (err: unknown) {
      setActionError(translateError(errorMessage(err)));
      void load(undefined, true);
    } finally {
      setAnalyzing(false);
    }
  };

  const handleExport = async (format: ExportFormat): Promise<void> => {
    if (!doc) return;
    setExportOpen(false);
    setExporting(format);
    setActionError(null);
    try {
      await exportDocument(doc.id, format);
    } catch (err: unknown) {
      setActionError(translateError(errorMessage(err)));
      void load(undefined, true);
    } finally {
      setExporting(null);
    }
  };

  const handleSave = async (): Promise<void> => {
    if (!doc || !page) return;
    if (pagePending > 0 && !window.confirm(t("saveWarnConfirm"))) return;
    setSaving(true);
    setActionError(null);
    try {
      await putPageText(doc.id, page.number, page.text);
      await load(undefined, true);
    } catch (err: unknown) {
      setActionError(translateError(errorMessage(err)));
    } finally {
      setSaving(false);
    }
  };

  const handleSuggestionStatus = async (
    suggestionId: number,
    status: SuggestionStatus,
  ): Promise<void> => {
    setBusySuggestionId(suggestionId);
    setActionError(null);
    try {
      const result = await patchSuggestion(suggestionId, status);
      replacePage(result.page);
    } catch (err: unknown) {
      setActionError(translateError(errorMessage(err)));
    } finally {
      setBusySuggestionId(null);
    }
  };

  /**
   * Musahhih modunda sayfa görseline tıklama: tıklanan noktadaki kelime
   * sunucuda bulunur ve işaretleme penceresi açılır.
   */
  const handleImageClick = async (
    event: React.MouseEvent<HTMLDivElement>,
  ): Promise<void> => {
    if (!musahhihMode || !doc || !page) return;
    const img = imageRef.current;
    if (!img || !page.width) return;
    const rect = img.getBoundingClientRect();
    if (rect.width <= 0) return;

    const scale = rect.width / page.width;
    const px = event.clientX - rect.left;
    const py = event.clientY - rect.top;
    const x = px / scale;
    const y = py / scale;

    setMarkBusy(true);
    setActionError(null);
    try {
      const hit = await wordAtPoint(doc.id, page.number, x, y);
      setMark({ px, py, hit, action: null, value: "" });
      if (!hit.found) {
        setActionError(t("musahhihNoWord"));
      }
    } catch (err: unknown) {
      setMark(null);
      setActionError(translateError(errorMessage(err)));
    } finally {
      setMarkBusy(false);
    }
  };

  /** Eyleme göre düzeltmenin ofsetlerini belirler. */
  const markOffsets = (
    hit: WordHit,
    mutation: CorrectionMutation,
  ): { start: number; end: number } => {
    if (mutation === "insert") return { start: hit.start, end: hit.start };
    if (mutation === "space") return { start: hit.end, end: hit.end };
    return { start: hit.start, end: hit.end };
  };

  /** Yazar işaretini kaydeder (düzeltme hemen metne uygulanır). */
  const submitMark = async (
    mutation: CorrectionMutation,
    replacement: string,
  ): Promise<void> => {
    if (!doc || !page || !mark) return;
    const offsets = markOffsets(mark.hit, mutation);
    setMarkBusy(true);
    setActionError(null);
    try {
      const result = await createCorrection(doc.id, {
        page_id: page.id,
        start: offsets.start,
        end: offsets.end,
        mutation,
        replacement,
      });
      replacePage(result.page);
      setMark(null);
    } catch (err: unknown) {
      setActionError(translateError(errorMessage(err)));
    } finally {
      setMarkBusy(false);
    }
  };

  const handleMarkAction = (action: CorrectionMutation): void => {
    if (!mark) return;
    if (action === "delete" || action === "space" || action === "join") {
      void submitMark(action, "");
      return;
    }
    // Değiştir / Ekle: yeni metin istenir
    setMark({ ...mark, action, value: "" });
  };

  const handleExportJson = async (): Promise<void> => {
    if (!doc) return;
    setExportingJson(true);
    setActionError(null);
    try {
      await exportCorrectionsJson(doc.id);
    } catch (err: unknown) {
      setActionError(translateError(errorMessage(err)));
    } finally {
      setExportingJson(false);
    }
  };

  /** Yazar işaretini kalıcı olarak siler. */
  const handleDeleteSuggestion = async (suggestionId: number): Promise<void> => {
    setBusySuggestionId(suggestionId);
    setActionError(null);
    try {
      await deleteSuggestion(suggestionId);
      await load(undefined, true);
    } catch (err: unknown) {
      setActionError(translateError(errorMessage(err)));
    } finally {
      setBusySuggestionId(null);
    }
  };

  const paneSkeleton = (
    <div className="pane">
      <div className="skeleton skeleton-line" style={{ width: "40%" }} />
      <div
        className="skeleton"
        style={{ height: 260, marginTop: 12, borderRadius: 6 }}
      />
    </div>
  );

  return (
    <div className="app-shell">
      <header className="review-topbar">
        <div className="topbar-left">
          <Link to="/" className="back-link">
            ← {t("back")}
          </Link>
          {doc && (
            <>
              <span className="topbar-title" title={doc.filename}>
                {doc.filename}
              </span>
              <span className={`badge badge-${doc.status}`}>
                {t(statusKey(doc.status))}
              </span>
            </>
          )}
        </div>
        <div className="topbar-actions">
          <button
            type="button"
            className="btn btn-primary"
            disabled={!doc || analyzing || !canAnalyze}
            onClick={() => void handleAnalyze()}
          >
            {analyzing && <span className="spinner" aria-hidden="true" />}
            {analyzing ? t("analyzing") : t("analyze")}
          </button>

          <button
            type="button"
            className={`btn ${musahhihMode ? "btn-active" : ""}`}
            aria-pressed={musahhihMode}
            disabled={!doc}
            onClick={() => {
              setMusahhihMode((on) => !on);
              setMark(null);
            }}
          >
            {t("musahhihBtn")}
          </button>

          <button
            type="button"
            className="btn"
            disabled={!doc || exportingJson}
            title={t("musahhihJsonHint")}
            onClick={() => void handleExportJson()}
          >
            {exportingJson && <span className="spinner" aria-hidden="true" />}
            {t("musahhihJsonBtn")}
          </button>

          <div className="dropdown">
            {exportOpen && (
              <button
                type="button"
                className="dropdown-backdrop"
                aria-hidden="true"
                tabIndex={-1}
                onClick={() => setExportOpen(false)}
              />
            )}
            <button
              type="button"
              className="btn"
              disabled={!doc || exporting !== null}
              onClick={() => setExportOpen((open) => !open)}
            >
              {exporting !== null
                ? t("exporting", { fmt: exporting.toUpperCase() })
                : t("exportBtn")}
            </button>
            {exportOpen && (
              <div className="dropdown-menu" role="menu">
                {EXPORT_FORMATS.map((format) => (
                  <button
                    key={format}
                    type="button"
                    className="dropdown-item"
                    role="menuitem"
                    onClick={() => void handleExport(format)}
                  >
                    {format.toUpperCase()}
                  </button>
                ))}
              </div>
            )}
          </div>

          <button
            type="button"
            className="btn"
            aria-pressed={changelogOpen}
            disabled={!doc}
            onClick={() => setChangelogOpen(true)}
          >
            {t("changeLogBtn")}
          </button>

          <button
            type="button"
            className="btn btn-ghost lang-toggle"
            aria-label={t("langToggle")}
            title={t("langToggle")}
            onClick={() => setLang(lang === "tr" ? "en" : "tr")}
          >
            {lang === "tr" ? "EN" : "TR"}
          </button>
        </div>
      </header>

      {doc?.analyzer_mode === "heuristic" && (
        <p className="heuristic-note">{t("heuristicNote")}</p>
      )}

      {doc && !musahhihMode && manualMarks === 0 && (
        <p className="musahhih-note">{t("musahhihSuggest")}</p>
      )}

      {doc && musahhihMode && (
        <div className="musahhih-banner" role="status">
          <span className="musahhih-banner-dot" aria-hidden="true" />
          <span>{t("musahhihHint")}</span>
          <button
            type="button"
            className="btn btn-ghost btn-small"
            onClick={() => {
              setMusahhihMode(false);
              setMark(null);
            }}
          >
            {t("musahhihCancel")}
          </button>
        </div>
      )}

      <main className="review-body">
        {loading && (
          <>
            {paneSkeleton}
            {paneSkeleton}
          </>
        )}

        {!loading && notFound && (
          <div className="empty-state" style={{ gridColumn: "1 / -1" }}>
            <p className="empty-state-title">{t("notFoundTitle")}</p>
            <p className="empty-state-text">{t("notFoundText")}</p>
            <p style={{ marginTop: 16 }}>
              <Link to="/" className="btn">
                ← {t("back")}
              </Link>
            </p>
          </div>
        )}

        {!loading && !notFound && loadError && (
          <div className="error-banner" style={{ gridColumn: "1 / -1" }}>
            <span>{loadError}</span>
          </div>
        )}

        {!loading && !notFound && !loadError && doc && (
          <>
            {/* ------------------------------------------------ left pane */}
            <section className="pane pane-left">
              <div className="pane-head">
                <h2 className="pane-title">{t("pagesNav")}</h2>
                <div className="image-tools">
                  <button
                    type="button"
                    className="btn btn-icon"
                    aria-label={t("zoomOut")}
                    title={t("zoomOut")}
                    disabled={zoom <= ZOOM_MIN}
                    onClick={() =>
                      setZoom((z) => Math.max(ZOOM_MIN, z - ZOOM_STEP))
                    }
                  >
                    −
                  </button>
                  <span className="zoom-label">{Math.round(zoom * 100)}%</span>
                  <button
                    type="button"
                    className="btn btn-icon"
                    aria-label={t("zoomIn")}
                    title={t("zoomIn")}
                    disabled={zoom >= ZOOM_MAX}
                    onClick={() =>
                      setZoom((z) => Math.min(ZOOM_MAX, z + ZOOM_STEP))
                    }
                  >
                    +
                  </button>
                </div>
              </div>

              {bubbles.length > 0 && (
                <div
                  className="bubble-legend"
                  aria-label={t("bubbleLegend")}
                  role="note"
                >
                  {LEGEND_ORDER.filter((type) =>
                    bubbles.some((bubble) => bubble.type === type),
                  ).map((type) => (
                    <span key={type} className="legend-item">
                      <span
                        className={`legend-dot bubble--${type}`}
                        aria-hidden="true"
                      >
                        {BUBBLE_SYMBOLS[type]}
                      </span>
                      {t(mutationKey(type))}
                    </span>
                  ))}
                </div>
              )}

              {doc.pages.length === 0 ? (
                <p className="guidance-note">{t("noPagesText")}</p>
              ) : (
                <div className="pages-shell">
                  <nav className="page-nav" aria-label={t("pagesNav")}>
                    {doc.pages.map((p, index) => {
                      const pending = pendingCountOnPage(p);
                      return (
                        <button
                          key={p.id}
                          type="button"
                          className={
                            index === activeIndex
                              ? "page-nav-btn active"
                              : "page-nav-btn"
                          }
                          onClick={() => setActiveIndex(index)}
                        >
                          <span>{p.number}</span>
                          {pending > 0 && (
                            <span className="badge badge-pending">
                              {pending}
                            </span>
                          )}
                        </button>
                      );
                    })}
                  </nav>

                  <div className="image-wrap">
                    {imageSrc && !imageFailed ? (
                      <>
                        <div
                          className={`image-frame${
                            musahhihMode ? " image-frame--marking" : ""
                          }`}
                          style={{ width: `${zoom * 100}%` }}
                          ref={frameRef}
                          onClick={(event) => void handleImageClick(event)}
                        >
                          <img
                            key={imageSrc}
                            ref={imageRef}
                            src={imageSrc}
                            alt={t("pageLabel", { n: page ? page.number : 0 })}
                            className="page-image"
                            onError={() => setImageFailed(true)}
                          />
                          {frameSize && placed.length > 0 && (
                            <svg
                              className="bubble-links"
                              width={frameSize.w}
                              height={frameSize.h}
                              viewBox={`0 0 ${frameSize.w} ${frameSize.h}`}
                              aria-hidden="true"
                            >
                              {placed.map((item) => (
                                <line
                                  key={item.suggestion.id}
                                  className={`bubble-line bubble--${item.type}`}
                                  x1={item.line.x1}
                                  y1={item.line.y1}
                                  x2={item.line.x2}
                                  y2={item.line.y2}
                                />
                              ))}
                            </svg>
                          )}
                          {placed.map((item) => (
                            <Fragment key={item.suggestion.id}>
                              <span
                                className={`rect-hl bubble--${item.type}${
                                  item.suggestion.id === selectedSuggestionId
                                    ? " is-selected"
                                    : ""
                                }`}
                                style={{
                                  left: item.box.x,
                                  top: item.box.y,
                                  width: item.box.w,
                                  height: item.box.h,
                                }}
                                aria-hidden="true"
                                onClick={(event) => {
                                  event.stopPropagation();
                                  selectSuggestion(item.suggestion.id);
                                }}
                              />
                              <button
                                type="button"
                                className={`bubble bubble--${item.type}${
                                  item.suggestion.id === selectedSuggestionId
                                    ? " bubble--active"
                                    : ""
                                }${
                                  item.suggestion.source === "manual"
                                    ? " bubble--manual"
                                    : ""
                                }`}
                                style={
                                  item.side === "left"
                                    ? { top: item.center, left: BUBBLE_INSET }
                                    : { top: item.center, right: BUBBLE_INSET }
                                }
                                title={bubbleTitle(item)}
                                aria-label={bubbleTitle(item)}
                                onClick={(event) => {
                                  event.stopPropagation();
                                  selectSuggestion(item.suggestion.id);
                                }}
                              >
                                {BUBBLE_SYMBOLS[item.type]}
                              </button>
                            </Fragment>
                          ))}

                          {mark && mark.hit.found && (
                            <div
                              className="mark-popover"
                              style={{
                                left: frameSize
                                  ? clampRange(
                                      mark.px,
                                      110,
                                      Math.max(110, frameSize.w - 110),
                                    )
                                  : mark.px,
                                top: mark.py,
                              }}
                              role="dialog"
                              aria-label={t("musahhihMarkTitle")}
                              onClick={(event) => event.stopPropagation()}
                            >
                              <div className="mark-popover-head">
                                <strong>{t("musahhihMarkTitle")}</strong>
                                <button
                                  type="button"
                                  className="btn btn-ghost btn-small"
                                  aria-label={t("musahhihCancel")}
                                  onClick={() => setMark(null)}
                                >
                                  ✕
                                </button>
                              </div>
                              <p className="mark-word">
                                <span>{t("musahhihWord")}:</span>{" "}
                                <code>{mark.hit.text}</code>
                              </p>
                              {mark.action === null ? (
                                <div className="mark-actions">
                                  {(
                                    [
                                      "delete",
                                      "replace",
                                      "insert",
                                      "space",
                                      "join",
                                    ] as CorrectionMutation[]
                                  ).map((action) => (
                                    <button
                                      key={action}
                                      type="button"
                                      className="btn btn-small"
                                      disabled={markBusy}
                                      onClick={() => handleMarkAction(action)}
                                    >
                                      {t(
                                        action === "delete"
                                          ? "actionDelete"
                                          : action === "replace"
                                            ? "actionReplace"
                                            : action === "insert"
                                              ? "actionInsert"
                                              : action === "space"
                                                ? "actionSpace"
                                                : "actionJoin",
                                      )}
                                    </button>
                                  ))}
                                </div>
                              ) : (
                                <div className="mark-form">
                                  <label className="mark-field">
                                    <span>{t("musahhihNewText")}</span>
                                    <input
                                      type="text"
                                      value={mark.value}
                                      autoFocus
                                      onChange={(event) =>
                                        setMark({
                                          ...mark,
                                          value: event.target.value,
                                        })
                                      }
                                      onKeyDown={(event) => {
                                        if (event.key === "Enter" && mark.action) {
                                          void submitMark(mark.action, mark.value);
                                        }
                                      }}
                                    />
                                  </label>
                                  <div className="mark-actions">
                                    <button
                                      type="button"
                                      className="btn btn-primary btn-small"
                                      disabled={markBusy || !mark.value.trim()}
                                      onClick={() => {
                                        if (mark.action)
                                          void submitMark(mark.action, mark.value);
                                      }}
                                    >
                                      {t("musahhihSubmit")}
                                    </button>
                                    <button
                                      type="button"
                                      className="btn btn-small"
                                      onClick={() =>
                                        setMark({ ...mark, action: null })
                                      }
                                    >
                                      {t("musahhihCancel")}
                                    </button>
                                  </div>
                                </div>
                              )}
                            </div>
                          )}
                        </div>
                        {page && !page.has_text && (
                          <div className="no-text-overlay">
                            {t("noTextOverlay")}
                          </div>
                        )}
                      </>
                    ) : (
                      <p
                        className="muted"
                        style={{ padding: 24, textAlign: "center" }}
                      >
                        {t("imageError")}
                      </p>
                    )}
                  </div>
                </div>
              )}
            </section>

            {/* ----------------------------------------------- right pane */}
            <section className="pane pane-right">
              {actionError && (
                <div className="error-banner">
                  <span>{actionError}</span>
                  <button
                    type="button"
                    className="btn btn-ghost btn-small"
                    onClick={() => setActionError(null)}
                  >
                    ✕
                  </button>
                </div>
              )}

              {doc.pages.length === 0 || allPagesTextless || !page ? (
                <p className="guidance-note">
                  {doc.pages.length === 0 || !page
                    ? t("noPagesText")
                    : t("noTextPagesText")}
                </p>
              ) : (
                <>
                  <div className="editor-row">
                    <h2 className="pane-title">
                      {t("pageLabel", { n: page.number })}
                    </h2>
                  </div>

                  <textarea
                    className="text-area"
                    value={page.text}
                    spellCheck={lang === "tr"}
                    onChange={(event) => handleTextChange(event.target.value)}
                  />

                  <div className="save-block">
                    <button
                      type="button"
                      className="btn btn-primary"
                      disabled={saving}
                      onClick={() => void handleSave()}
                    >
                      {saving && <span className="spinner" aria-hidden="true" />}
                      {saving ? t("saving") : t("save")}
                    </button>
                    {pagePending > 0 && (
                      <span className="warn-note">{t("saveWarn")}</span>
                    )}
                  </div>

                  <div className="suggestions-head">
                    <h2 className="pane-title">{t("suggestionsTitle")}</h2>
                    {pagePending > 0 && (
                      <span className="badge badge-pending">
                        {t("pendingValue", { n: pagePending })}
                      </span>
                    )}
                  </div>

                  {page.suggestions.length === 0 ? (
                    <p className="muted">{t("emptySuggestions")}</p>
                  ) : (
                    <div className="suggestions-list">
                      {page.suggestions.map((suggestion) => (
                        <SuggestionCard
                          key={suggestion.id}
                          suggestion={suggestion}
                          busy={busySuggestionId === suggestion.id}
                          selected={selectedSuggestionId === suggestion.id}
                          onSelect={(suggestionId) =>
                            setSelectedSuggestionId(suggestionId)
                          }
                          onAccept={(suggestionId) =>
                            void handleSuggestionStatus(suggestionId, "accepted")
                          }
                          onReject={(suggestionId) =>
                            void handleSuggestionStatus(suggestionId, "rejected")
                          }
                          onUndo={(suggestionId) =>
                            void handleSuggestionStatus(suggestionId, "pending")
                          }
                          onDelete={(suggestionId) =>
                            void handleDeleteSuggestion(suggestionId)
                          }
                        />
                      ))}
                    </div>
                  )}
                </>
              )}
            </section>
          </>
        )}
      </main>

      {doc && (
        <ChangeLogPanel
          docId={doc.id}
          open={changelogOpen}
          onClose={() => setChangelogOpen(false)}
        />
      )}
    </div>
  );
}
