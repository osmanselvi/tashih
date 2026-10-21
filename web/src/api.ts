import type {
  ChangeLogEntry,
  CorrectionCreate,
  DocumentDetail,
  DocSummary,
  ExportFormat,
  Page,
  SuggestionResult,
  SuggestionStatus,
  WordHit,
} from "./types";

export class ApiError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

export function isAbortError(error: unknown): boolean {
  return (
    typeof error === "object" &&
    error !== null &&
    "name" in error &&
    (error as { name: unknown }).name === "AbortError"
  );
}

export function errorMessage(error: unknown): string {
  if (error instanceof Error) return error.message;
  return String(error);
}

async function toApiError(response: Response): Promise<ApiError> {
  let detail = `HTTP ${response.status}`;
  try {
    const data: unknown = await response.json();
    if (typeof data === "object" && data !== null && "detail" in data) {
      const value = (data as { detail: unknown }).detail;
      if (typeof value === "string" && value.trim() !== "") detail = value;
    }
  } catch {
    // Non-JSON error body; keep the HTTP fallback.
  }
  return new ApiError(response.status, detail);
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, init);
  if (!response.ok) throw await toApiError(response);
  return (await response.json()) as T;
}

export function getHealth(signal?: AbortSignal): Promise<{ status: string }> {
  return request<{ status: string }>("/api/health", { signal });
}

export function listDocuments(signal?: AbortSignal): Promise<DocSummary[]> {
  return request<DocSummary[]>("/api/documents", { signal });
}

export function uploadDocument(
  file: File,
  signal?: AbortSignal,
): Promise<DocumentDetail> {
  const form = new FormData();
  form.append("file", file);
  return request<DocumentDetail>("/api/documents", {
    method: "POST",
    body: form,
    signal,
  });
}

export function getDocument(
  id: number,
  signal?: AbortSignal,
): Promise<DocumentDetail> {
  return request<DocumentDetail>(`/api/documents/${id}`, { signal });
}

export function deleteDocument(
  id: number,
  signal?: AbortSignal,
): Promise<{ ok: boolean }> {
  return request<{ ok: boolean }>(`/api/documents/${id}`, {
    method: "DELETE",
    signal,
  });
}

export function analyzeDocument(
  id: number,
  pageNumbers?: number[],
  signal?: AbortSignal,
): Promise<DocumentDetail> {
  const body: { page_numbers?: number[] } = {};
  if (pageNumbers && pageNumbers.length > 0) body.page_numbers = pageNumbers;
  return request<DocumentDetail>(`/api/documents/${id}/analyze`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal,
  });
}

/** Direct URL for the page PNG, usable as an <img src>. */
export function pageImageUrl(id: number, pageNumber: number): string {
  return `/api/documents/${id}/pages/${pageNumber}/image`;
}

export function patchSuggestion(
  id: number,
  status: SuggestionStatus,
  signal?: AbortSignal,
): Promise<SuggestionResult> {
  return request<SuggestionResult>(`/api/suggestions/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ status }),
    signal,
  });
}

export function putPageText(
  id: number,
  pageNumber: number,
  text: string,
  signal?: AbortSignal,
): Promise<Page> {
  return request<Page>(`/api/documents/${id}/pages/${pageNumber}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text }),
    signal,
  });
}

/** Yazar (musahhih) işareti oluşturur; düzeltme hemen metne uygulanır. */
export function createCorrection(
  id: number,
  payload: CorrectionCreate,
  signal?: AbortSignal,
): Promise<SuggestionResult> {
  return request<SuggestionResult>(`/api/documents/${id}/corrections`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
    signal,
  });
}

/** Sayfa görselinde tıklanan noktadaki kelimeyi bulur (PDF puanı koordinatı). */
export function wordAtPoint(
  id: number,
  pageNumber: number,
  x: number,
  y: number,
  signal?: AbortSignal,
): Promise<WordHit> {
  return request<WordHit>(
    `/api/documents/${id}/pages/${pageNumber}/word-at`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ x, y }),
      signal,
    },
  );
}

export function deleteSuggestion(
  id: number,
  signal?: AbortSignal,
): Promise<{ ok: boolean }> {
  return request<{ ok: boolean }>(`/api/suggestions/${id}`, {
    method: "DELETE",
    signal,
  });
}

function contentDispositionFilename(header: string | null): string | null {
  if (!header) return null;
  const utf8 = /filename\*\s*=\s*UTF-8''([^;]+)/i.exec(header);
  if (utf8 && utf8[1]) {
    try {
      return decodeURIComponent(utf8[1].trim());
    } catch {
      // Fall through to the plain filename.
    }
  }
  const plain = /filename\s*=\s*"?([^";]+)"?/i.exec(header);
  return plain && plain[1] ? plain[1].trim() : null;
}

export async function exportDocument(
  id: number,
  format: ExportFormat,
): Promise<void> {
  const response = await fetch(`/api/documents/${id}/export`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ format }),
  });
  if (!response.ok) throw await toApiError(response);

  const blob = await response.blob();
  const filename =
    contentDispositionFilename(response.headers.get("Content-Disposition")) ??
    `tashih-${id}.${format}`;

  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

export function getChangelog(
  id: number,
  signal?: AbortSignal,
): Promise<ChangeLogEntry[]> {
  return request<ChangeLogEntry[]>(`/api/documents/${id}/changelog`, { signal });
}

/**
 * Musahhih işaretlerini (ve yapay zekâ önerilerini) JSON dosyasına aktarır.
 * Biçim, masaüstü "Musahhih" uygulamasının okuyabildiği şemayla uyumludur.
 */
export async function exportCorrectionsJson(id: number): Promise<void> {
  const response = await fetch(`/api/documents/${id}/corrections.json`);
  if (!response.ok) throw await toApiError(response);

  const blob = await response.blob();
  const filename =
    contentDispositionFilename(response.headers.get("Content-Disposition")) ??
    `tashih-${id}.json`;

  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}
