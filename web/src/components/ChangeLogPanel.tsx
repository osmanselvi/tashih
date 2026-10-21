import { useEffect, useState } from "react";
import { errorMessage, getChangelog, isAbortError } from "../api";
import { formatDate, t, translateError, useLang } from "../i18n";
import type { ChangeLogEntry } from "../types";

interface ChangeLogPanelProps {
  docId: number;
  open: boolean;
  onClose: () => void;
}

export default function ChangeLogPanel({
  docId,
  open,
  onClose,
}: ChangeLogPanelProps) {
  const lang = useLang();
  const [entries, setEntries] = useState<ChangeLogEntry[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    const controller = new AbortController();
    setLoading(true);
    setError(null);
    getChangelog(docId, controller.signal)
      .then(setEntries)
      .catch((err: unknown) => {
        if (!isAbortError(err)) setError(translateError(errorMessage(err)));
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [open, docId]);

  useEffect(() => {
    if (!open) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [open, onClose]);

  return (
    <div
      className={open ? "changelog-overlay open" : "changelog-overlay"}
      aria-hidden={!open}
    >
      <button
        type="button"
        className="changelog-backdrop"
        aria-label={t("changelogClose")}
        onClick={onClose}
      />
      <aside
        className="changelog-panel"
        role="dialog"
        aria-modal="true"
        aria-label={t("changelogTitle")}
      >
        <header className="changelog-head">
          <h2>{t("changelogTitle")}</h2>
          <button type="button" className="btn btn-ghost" onClick={onClose}>
            {t("changelogClose")}
          </button>
        </header>
        <div className="changelog-body">
          {error && <div className="error-banner">{error}</div>}
          {loading && <p className="muted">{t("loading")}</p>}
          {!loading && !error && entries !== null && entries.length === 0 && (
            <p className="muted">{t("changelogEmpty")}</p>
          )}
          {entries !== null && entries.length > 0 && (
            <ul className="changelog-list">
              {entries.map((entry) => (
                <li key={entry.id} className="changelog-item">
                  <div className="changelog-meta">
                    <span className="changelog-page">
                      {t("pageLabel", { n: entry.page_number })}
                    </span>
                    <span className={`source-badge source-${entry.source}`}>
                      {entry.source === "ai" ? t("sourceAi") : t("sourceManual")}
                    </span>
                    <time dateTime={entry.created_at}>
                      {formatDate(entry.created_at, lang)}
                    </time>
                  </div>
                  <p className="changelog-diff">
                    <span className="changelog-old">{entry.old_text}</span>
                    <span className="changelog-new">{entry.new_text}</span>
                  </p>
                </li>
              ))}
            </ul>
          )}
        </div>
      </aside>
    </div>
  );
}
