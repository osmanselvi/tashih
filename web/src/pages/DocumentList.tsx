import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  deleteDocument,
  errorMessage,
  isAbortError,
  listDocuments,
  uploadDocument,
} from "../api";
import {
  formatDate,
  setLang,
  statusKey,
  t,
  translateError,
  useLang,
} from "../i18n";
import type { MouseEvent } from "react";
import type { DocSummary } from "../types";

export default function DocumentList() {
  const lang = useLang();
  const navigate = useNavigate();

  const [docs, setDocs] = useState<DocSummary[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [listError, setListError] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [dragActive, setDragActive] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const controller = new AbortController();
    listDocuments(controller.signal)
      .then(setDocs)
      .catch((err: unknown) => {
        if (!isAbortError(err)) {
          setListError(translateError(errorMessage(err)));
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, []);

  const handleFiles = async (files: FileList | null): Promise<void> => {
    const file = files?.[0];
    if (!file) return;
    const looksLikePdf =
      file.type === "application/pdf" ||
      file.name.toLowerCase().endsWith(".pdf");
    if (!looksLikePdf) {
      setUploadError(t("errNotPdf"));
      return;
    }
    setUploading(true);
    setUploadError(null);
    try {
      const created = await uploadDocument(file);
      navigate(`/documents/${created.id}`);
    } catch (err: unknown) {
      setUploadError(translateError(errorMessage(err)));
    } finally {
      setUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  };

  const handleDelete = async (
    event: MouseEvent,
    doc: DocSummary,
  ): Promise<void> => {
    event.stopPropagation();
    if (!window.confirm(t("deleteConfirm"))) return;
    try {
      await deleteDocument(doc.id);
      setDocs((current) =>
        current ? current.filter((d) => d.id !== doc.id) : current,
      );
    } catch (err: unknown) {
      setListError(translateError(errorMessage(err)));
    }
  };

  const openPicker = (): void => {
    fileInputRef.current?.click();
  };

  return (
    <div className="app-shell">
      <header className="app-header">
        <div className="brand">
          <span className="brand-name">{t("appName")}</span>
          <span className="brand-tagline">{t("tagline")}</span>
        </div>
        <button
          type="button"
          className="btn btn-ghost lang-toggle"
          aria-label={t("langToggle")}
          title={t("langToggle")}
          onClick={() => setLang(lang === "tr" ? "en" : "tr")}
        >
          {lang === "tr" ? "EN" : "TR"}
        </button>
      </header>

      <main className="page-container">
        <div
          className={dragActive ? "upload-zone dragover" : "upload-zone"}
          onDragOver={(event) => {
            event.preventDefault();
            setDragActive(true);
          }}
          onDragLeave={() => setDragActive(false)}
          onDrop={(event) => {
            event.preventDefault();
            setDragActive(false);
            void handleFiles(event.dataTransfer.files);
          }}
          onClick={openPicker}
        >
          <p className="upload-zone-title">{t("uploadZoneTitle")}</p>
          <p className="upload-hint">{t("uploadZoneHint")}</p>
          <div className="upload-actions">
            <button
              type="button"
              className="btn btn-primary"
              disabled={uploading}
              onClick={(event) => {
                event.stopPropagation();
                openPicker();
              }}
            >
              {uploading && <span className="spinner" aria-hidden="true" />}
              {uploading ? t("uploading") : t("uploadButton")}
            </button>
          </div>
          <input
            ref={fileInputRef}
            className="hidden-input"
            type="file"
            accept="application/pdf"
            onChange={(event) => void handleFiles(event.target.files)}
          />
        </div>

        {uploadError && (
          <div className="error-banner" style={{ marginTop: 16 }}>
            <span>{uploadError}</span>
            <button
              type="button"
              className="btn btn-ghost btn-small"
              onClick={() => setUploadError(null)}
            >
              ✕
            </button>
          </div>
        )}

        <div className="section-head">
          <h2 className="section-title">{t("listTitle")}</h2>
        </div>

        {listError && (
          <div className="error-banner">
            <span>{listError}</span>
            <button
              type="button"
              className="btn btn-ghost btn-small"
              onClick={() => setListError(null)}
            >
              ✕
            </button>
          </div>
        )}

        {loading && (
          <div className="loading-row">
            <span className="spinner spinner-lg" aria-hidden="true" />
            <span>{t("loading")}</span>
          </div>
        )}

        {!loading && docs !== null && docs.length === 0 && (
          <div className="empty-state">
            <p className="empty-state-title">{t("emptyDocsTitle")}</p>
            <p className="empty-state-text">{t("emptyDocsText")}</p>
          </div>
        )}

        {!loading && docs !== null && docs.length > 0 && (
          <div className="table-card">
            <table className="doc-table">
              <thead>
                <tr>
                  <th>{t("colFilename")}</th>
                  <th>{t("colStatus")}</th>
                  <th>{t("colPages")}</th>
                  <th>{t("colPending")}</th>
                  <th>{t("colCreated")}</th>
                  <th aria-label={t("colActions")} />
                </tr>
              </thead>
              <tbody>
                {docs.map((doc) => (
                  <tr
                    key={doc.id}
                    className="row-clickable"
                    tabIndex={0}
                    onClick={() => navigate(`/documents/${doc.id}`)}
                    onKeyDown={(event) => {
                      if (event.key === "Enter") {
                        navigate(`/documents/${doc.id}`);
                      }
                    }}
                  >
                    <td className="cell-filename">{doc.filename}</td>
                    <td>
                      <span className={`badge badge-${doc.status}`}>
                        {t(statusKey(doc.status))}
                      </span>
                    </td>
                    <td>{t("pagesValue", { n: doc.page_count })}</td>
                    <td>
                      {doc.pending_count > 0 ? (
                        <span className="badge badge-pending">
                          {t("pendingValue", { n: doc.pending_count })}
                        </span>
                      ) : (
                        <span className="muted">—</span>
                      )}
                    </td>
                    <td className="cell-created">
                      {formatDate(doc.created_at, lang)}
                    </td>
                    <td>
                      <button
                        type="button"
                        className="btn btn-danger btn-small"
                        aria-label={t("deleteDoc")}
                        title={t("deleteDoc")}
                        onClick={(event) => void handleDelete(event, doc)}
                      >
                        ✕
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </main>
    </div>
  );
}
