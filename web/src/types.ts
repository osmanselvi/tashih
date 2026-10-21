export type DocStatus =
  | "extracted"
  | "analyzing"
  | "analyzed"
  | "reviewing"
  | "done";

export type SuggestionStatus = "pending" | "accepted" | "rejected";

export type SuggestionKind =
  | "spelling"
  | "grammar"
  | "punctuation"
  | "ocr"
  | "style"
  | "manual";

/** Düzeltmenin kaynağı: kural/LLM önerisi ya da yazar (musahhih) işareti. */
export type SuggestionSource = "ai" | "manual";

export type ExportFormat = "txt" | "md" | "docx";

export interface DocSummary {
  id: number;
  filename: string;
  status: DocStatus;
  page_count: number;
  created_at: string;
  pending_count: number;
}

export interface Suggestion {
  id: number;
  page_id: number;
  kind: SuggestionKind;
  original: string;
  replacement: string;
  start: number;
  end: number;
  explanation: string;
  status: SuggestionStatus;
  /**
   * [x0, y0, x1, y1] in PDF page points; origin TOP-LEFT, y grows downward.
   * null = not located (old data).
   */
  rect: [number, number, number, number] | null;
  /** "ai" = kural/LLM önerisi, "manual" = yazar (musahhih) işareti. */
  source: SuggestionSource;
  /** Manuel işaretlerde düzeltmenin türü (AI önerilerinde null). */
  mutation: MutationType | null;
}

export interface Page {
  id: number;
  number: number;
  text: string;
  original_text: string;
  has_text: boolean;
  suggestions: Suggestion[];
  /** PDF page width in points (same space as Suggestion.rect) */
  width: number | null;
  /** PDF page height in points */
  height: number | null;
}

/** Visual/semantic category of a correction. */
export type MutationType = "delete" | "insert" | "replace" | "space" | "join";

export function mutationType(
  suggestion: Pick<Suggestion, "original" | "replacement" | "mutation">,
): MutationType {
  // Yazar işaretlerinde tür açık olarak saklanır (boşluk/birleştirme de var)
  if (suggestion.mutation) return suggestion.mutation;
  if (suggestion.original !== "" && suggestion.replacement === "") {
    return "delete";
  }
  if (suggestion.original === "" && suggestion.replacement !== "") {
    return "insert";
  }
  return "replace";
}

/** Musahhih işaretinde kullanılan düzeltme türleri. */
export type CorrectionMutation = "delete" | "insert" | "replace" | "space" | "join";

export interface CorrectionCreate {
  page_id: number;
  start: number;
  end: number;
  mutation: CorrectionMutation;
  replacement: string;
}

/** Sayfa görselinde tıklanan noktadaki kelime. */
export interface WordHit {
  found: boolean;
  start: number;
  end: number;
  text: string;
  rect: [number, number, number, number] | null;
}

export interface DocumentDetail extends DocSummary {
  pages: Page[];
  analyzer_mode?: "llm" | "heuristic";
}

export interface ChangeLogEntry {
  id: number;
  page_number: number;
  old_text: string;
  new_text: string;
  source: "manual" | "ai";
  created_at: string;
}

export interface SuggestionResult {
  suggestion: Suggestion;
  page: Page;
}
