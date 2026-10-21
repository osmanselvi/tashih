import { useSyncExternalStore } from "react";
import type {
  DocStatus,
  MutationType,
  SuggestionKind,
  SuggestionStatus,
} from "./types";

export type Lang = "tr" | "en";

const tr = {
  appName: "Tashih",
  tagline: "Musahhihlik Masası",
  langToggle: "Dili değiştir",

  back: "Tüm belgeler",
  loading: "Yükleniyor…",
  genericError: "Bir hata oluştu",

  // Document list
  listTitle: "Belgeler",
  uploadZoneTitle: "PDF dosyasını buraya sürükleyip bırakın",
  uploadZoneHint: "veya dosya seçmek için tıklayın",
  uploadButton: "PDF yükle",
  uploading: "Yükleniyor…",
  colFilename: "Dosya adı",
  colStatus: "Durum",
  colPages: "Sayfa",
  colPending: "Bekleyen",
  colCreated: "Oluşturulma",
  colActions: "İşlem",
  pagesValue: "{n} sayfa",
  pendingValue: "{n} bekleyen",
  deleteDoc: "Belgeyi sil",
  deleteConfirm: "Bu belge kalıcı olarak silinsin mi?",
  emptyDocsTitle: "Henüz belge yok",
  emptyDocsText: "Yukarıdan bir PDF yükleyerek musahhihlik masasına başlayın.",

  // Document statuses
  statusExtracted: "Çıkarıldı",
  statusAnalyzing: "Analiz ediliyor",
  statusAnalyzed: "Analiz edildi",
  statusReviewing: "İnceleniyor",
  statusDone: "Tamamlandı",

  // Review workbench
  analyze: "Yapay zekâ ile analiz et",
  analyzing: "Analiz ediliyor…",
  exportBtn: "Dışa aktar",
  exporting: "{fmt} hazırlanıyor…",
  changeLogBtn: "Değişiklik günlüğü",
  heuristicNote:
    "Yapay zekâ anahtarı yapılandırılmamış; kural tabanlı analiz kullanıldı.",
  noPagesText: "Bu belgede çıkarılmış sayfa yok.",
  noTextPagesText:
    "Belgede hiçbir sayfada metin katmanı bulunamadı. Tarama (OCR) sonrası tekrar deneyin.",
  pagesNav: "Sayfalar",
  zoomIn: "Yakınlaştır",
  zoomOut: "Uzaklaştır",
  pageLabel: "Sayfa {n}",
  noTextOverlay: "Bu sayfada metin katmanı yok (taranmış sayfa)",
  imageError: "Sayfa görseli yüklenemedi",
  save: "Kaydet",
  saving: "Kaydediliyor…",
  saveWarn: "Kaydetmek beklenen önerileri kaldırır.",
  saveWarnConfirm:
    "Kaydetmek beklenen önerileri kaldırır. Devam edilsin mi?",
  suggestionsTitle: "Öneriler",
  emptySuggestions: "Bu sayfa için öneri yok",

  // Suggestion kinds
  kindSpelling: "Yazım",
  kindGrammar: "Dilbilgisi",
  kindPunctuation: "Noktalama",
  kindOcr: "OCR",
  kindStyle: "Üslup",
  kindManual: "Musahhih",

  // Image bubbles / legend
  bubbleDelete: "Silme",
  bubbleInsert: "Ekleme",
  bubbleReplace: "Değiştirme",
  bubbleSpace: "Boşluk",
  bubbleJoin: "Birleştirme",
  bubbleLegend: "Gösterge",

  // Musahhih (yazar) kontrolü
  musahhihBtn: "Musahhih kontrolü",
  musahhihModeOn: "Musahhih kontrolü açık",
  musahhihSuggest:
    "İsterseniz önce “Musahhih kontrolü” ile kendi göz kontrolünüzü yapabilirsiniz.",
  musahhihHint:
    "Musahhih kontrolü açık: hatayı sayfa görseline tıklayarak işaretleyin.",
  musahhihHintShort:
    "Hatayı sayfa görseline tıklayarak işaretleyin.",
  musahhihJsonBtn: "JSON indir",
  musahhihJsonHint:
    "Düzeltmeler JSON dosyasına aktarılır (musahhih uygulamasıyla uyumlu).",
  musahhihMarkTitle: "Düzeltme ekle",
  musahhihWord: "Tıklanan kelime",
  musahhihNoWord: "Bu noktada metin bulunamadı.",
  musahhihNewText: "Yeni metin",
  musahhihNote: "Not (isteğe bağlı)",
  musahhihSubmit: "Kaydet",
  musahhihCancel: "Vazgeç",
  musahhihMarks: "{n} işaret",
  actionDelete: "Sil",
  actionReplace: "Değiştir",
  actionInsert: "Ekle",
  actionSpace: "Boşluk",
  actionJoin: "Birleştir",
  deleteMark: "İşareti sil",

  // Suggestion actions / statuses
  accept: "Kabul et",
  reject: "Reddet",
  undo: "Geri al",
  sugPending: "Beklemede",
  sugAccepted: "Kabul edildi",
  sugRejected: "Reddedildi",

  // Change log
  changelogTitle: "Değişiklik günlüğü",
  changelogEmpty: "Kayıtlı değişiklik yok.",
  changelogClose: "Kapat",
  sourceAi: "Yapay zekâ",
  sourceManual: "Elle",

  // Document not found
  notFoundTitle: "Belge bulunamadı",
  notFoundText: "Aradığınız belge mevcut değil veya silinmiş olabilir.",

  // Known backend error details (translated, others shown raw)
  errDocumentNotFound: "Belge bulunamadı.",
  errNotPdf: "Yalnızca PDF dosyaları yüklenebilir.",
  errNoTextLayer: "Belgede metin katmanı bulunamadı.",
  errAnalyzeFailed: "Analiz başarısız oldu.",
  errExportFailed: "Dışa aktarma başarısız oldu.",
} satisfies Record<string, string>;

type Key = keyof typeof tr;

const en: Record<Key, string> = {
  appName: "Tashih",
  tagline: "Proofreading Workbench",
  langToggle: "Switch language",

  back: "All documents",
  loading: "Loading…",
  genericError: "Something went wrong",

  // Document list
  listTitle: "Documents",
  uploadZoneTitle: "Drop a PDF file here",
  uploadZoneHint: "or click to choose a file",
  uploadButton: "Upload PDF",
  uploading: "Uploading…",
  colFilename: "Filename",
  colStatus: "Status",
  colPages: "Pages",
  colPending: "Pending",
  colCreated: "Created",
  colActions: "Actions",
  pagesValue: "{n} pages",
  pendingValue: "{n} pending",
  deleteDoc: "Delete document",
  deleteConfirm: "Delete this document permanently?",
  emptyDocsTitle: "No documents yet",
  emptyDocsText: "Upload a PDF above to start proofreading.",

  // Document statuses
  statusExtracted: "Extracted",
  statusAnalyzing: "Analyzing",
  statusAnalyzed: "Analyzed",
  statusReviewing: "Reviewing",
  statusDone: "Done",

  // Review workbench
  analyze: "Analyze with AI",
  analyzing: "Analyzing…",
  exportBtn: "Export",
  exporting: "Preparing {fmt}…",
  changeLogBtn: "Change log",
  heuristicNote:
    "No AI key configured; rule-based analysis was used.",
  noPagesText: "No pages were extracted from this document.",
  noTextPagesText:
    "No page in this document has a text layer. Try again after OCR.",
  pagesNav: "Pages",
  zoomIn: "Zoom in",
  zoomOut: "Zoom out",
  pageLabel: "Page {n}",
  noTextOverlay: "No text layer on this page (scanned page)",
  imageError: "Could not load the page image",
  save: "Save",
  saving: "Saving…",
  saveWarn: "Saving will discard pending suggestions on this page.",
  saveWarnConfirm:
    "Saving will discard pending suggestions on this page. Continue?",
  suggestionsTitle: "Suggestions",
  emptySuggestions: "No suggestions for this page",

  // Suggestion kinds
  kindSpelling: "Spelling",
  kindGrammar: "Grammar",
  kindPunctuation: "Punctuation",
  kindOcr: "OCR",
  kindStyle: "Style",
  kindManual: "Proofreader",

  // Image bubbles / legend
  bubbleDelete: "Deletion",
  bubbleInsert: "Insertion",
  bubbleReplace: "Replacement",
  bubbleSpace: "Space",
  bubbleJoin: "Join",
  bubbleLegend: "Legend",

  // Musahhih (proofreader) review
  musahhihBtn: "Proofreader review",
  musahhihModeOn: "Proofreader review is on",
  musahhihSuggest:
    "You can do your own review first with “Proofreader review”.",
  musahhihHint:
    "Proofreader review is on: click an error on the page image to mark it.",
  musahhihHintShort: "Click an error on the page image to mark it.",
  musahhihJsonBtn: "Download JSON",
  musahhihJsonHint:
    "Corrections are exported to a JSON file (compatible with the Musahhih app).",
  musahhihMarkTitle: "Add correction",
  musahhihWord: "Clicked word",
  musahhihNoWord: "No text found at this point.",
  musahhihNewText: "New text",
  musahhihNote: "Note (optional)",
  musahhihSubmit: "Save",
  musahhihCancel: "Cancel",
  musahhihMarks: "{n} marks",
  actionDelete: "Delete",
  actionReplace: "Replace",
  actionInsert: "Insert",
  actionSpace: "Space",
  actionJoin: "Join",
  deleteMark: "Delete mark",

  // Suggestion actions / statuses
  accept: "Accept",
  reject: "Reject",
  undo: "Undo",
  sugPending: "Pending",
  sugAccepted: "Accepted",
  sugRejected: "Rejected",

  // Change log
  changelogTitle: "Change log",
  changelogEmpty: "No recorded changes.",
  changelogClose: "Close",
  sourceAi: "AI",
  sourceManual: "Manual",

  // Document not found
  notFoundTitle: "Document not found",
  notFoundText: "The document does not exist or may have been deleted.",

  // Known backend error details (translated, others shown raw)
  errDocumentNotFound: "Document not found.",
  errNotPdf: "Only PDF files can be uploaded.",
  errNoTextLayer: "No text layer found in the document.",
  errAnalyzeFailed: "Analysis failed.",
  errExportFailed: "Export failed.",
};

const dictionaries: Record<Lang, Record<Key, string>> = { tr, en };

type Listener = () => void;
const listeners = new Set<Listener>();

function readStoredLang(): Lang {
  try {
    return localStorage.getItem("tashih.lang") === "en" ? "en" : "tr";
  } catch {
    return "tr";
  }
}

let currentLang: Lang = readStoredLang();

export function getLang(): Lang {
  return currentLang;
}

export function setLang(lang: Lang): void {
  if (lang === currentLang) return;
  currentLang = lang;
  try {
    localStorage.setItem("tashih.lang", lang);
  } catch {
    // storage unavailable; keep in-memory language
  }
  document.documentElement.lang = lang;
  for (const listener of listeners) listener();
}

export function subscribeLang(listener: Listener): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

/** Re-renders the component whenever the language changes. */
export function useLang(): Lang {
  return useSyncExternalStore(subscribeLang, getLang);
}

export function t(key: Key, vars?: Record<string, string | number>): string {
  let text: string = dictionaries[currentLang][key];
  if (vars) {
    for (const [name, value] of Object.entries(vars)) {
      text = text.split(`{${name}}`).join(String(value));
    }
  }
  return text;
}

export function statusKey(status: DocStatus): Key {
  switch (status) {
    case "extracted":
      return "statusExtracted";
    case "analyzing":
      return "statusAnalyzing";
    case "analyzed":
      return "statusAnalyzed";
    case "reviewing":
      return "statusReviewing";
    case "done":
      return "statusDone";
  }
}

export function suggestionStatusKey(status: SuggestionStatus): Key {
  switch (status) {
    case "pending":
      return "sugPending";
    case "accepted":
      return "sugAccepted";
    case "rejected":
      return "sugRejected";
  }
}

export function kindKey(kind: SuggestionKind): Key {
  switch (kind) {
    case "spelling":
      return "kindSpelling";
    case "grammar":
      return "kindGrammar";
    case "punctuation":
      return "kindPunctuation";
    case "ocr":
      return "kindOcr";
    case "style":
      return "kindStyle";
    case "manual":
      return "kindManual";
  }
}

export function mutationKey(type: MutationType): Key {
  switch (type) {
    case "delete":
      return "bubbleDelete";
    case "insert":
      return "bubbleInsert";
    case "replace":
      return "bubbleReplace";
    case "space":
      return "bubbleSpace";
    case "join":
      return "bubbleJoin";
  }
}

/** Locale string for a language, e.g. "tr-TR" / "en-US". */
export function localeFor(lang: Lang): string {
  return lang === "tr" ? "tr-TR" : "en-US";
}

export function formatDate(iso: string, lang: Lang): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleString(localeFor(lang), {
    dateStyle: "medium",
    timeStyle: "short",
  });
}

/** Translates known backend {detail} strings; unknown ones pass through raw. */
const errorDetailMap: Record<string, Key> = {
  "document not found": "errDocumentNotFound",
  "doc not found": "errDocumentNotFound",
  "file must be a pdf": "errNotPdf",
  "only pdf files are allowed": "errNotPdf",
  "no text layer found": "errNoTextLayer",
  "analysis failed": "errAnalyzeFailed",
  "export failed": "errExportFailed",
};

export function translateError(detail: string): string {
  const key = errorDetailMap[detail.trim().toLowerCase()];
  return key ? t(key) : detail;
}
