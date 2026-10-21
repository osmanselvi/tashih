import { kindKey, suggestionStatusKey, t } from "../i18n";
import { mutationType } from "../types";
import type { KeyboardEvent, MouseEvent } from "react";
import type { Suggestion } from "../types";

interface SuggestionCardProps {
  suggestion: Suggestion;
  busy: boolean;
  selected: boolean;
  onSelect: (suggestionId: number) => void;
  onAccept: (suggestionId: number) => void;
  onReject: (suggestionId: number) => void;
  onUndo: (suggestionId: number) => void;
  /** Yazar işaretlerini kalıcı olarak silmek için (isteğe bağlı). */
  onDelete?: (suggestionId: number) => void;
}

function cardClassName(
  suggestion: Suggestion,
  selected: boolean,
): string {
  const classes = ["suggestion-card", suggestion.status];
  if (suggestion.status === "pending") {
    classes.push(`suggestion-card--accent-${mutationType(suggestion)}`);
  }
  if (suggestion.source === "manual") classes.push("suggestion-card--manual");
  if (selected) classes.push("suggestion-card--selected");
  return classes.join(" ");
}

export default function SuggestionCard({
  suggestion,
  busy,
  selected,
  onSelect,
  onAccept,
  onReject,
  onUndo,
  onDelete,
}: SuggestionCardProps) {
  const { id, kind, original, replacement, explanation, status } = suggestion;
  const manual = suggestion.source === "manual";

  const handleCardClick = (): void => onSelect(id);
  const handleCardKeyDown = (event: KeyboardEvent<HTMLDivElement>): void => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      onSelect(id);
    }
  };
  const stopPropagation = (event: MouseEvent<HTMLButtonElement>): void => {
    event.stopPropagation();
  };

  const cardRole = {
    id: `suggestion-${id}`,
    className: cardClassName(suggestion, selected),
    tabIndex: 0,
    onClick: handleCardClick,
    onKeyDown: handleCardKeyDown,
  };

  if (status === "rejected") {
    return (
      <div {...cardRole}>
        <div className="suggestion-head">
          <span className={`kind-badge kind-${kind}`}>{t(kindKey(kind))}</span>
          <span className="suggestion-state">
            {t(suggestionStatusKey(status))}
          </span>
        </div>
        <div className="suggestion-collapsed">
          <span className="suggestion-original">{original}</span>
          <span className="suggestion-arrow" aria-hidden="true">
            →
          </span>
          <span className="suggestion-replacement">{replacement}</span>
          <button
            type="button"
            className="btn btn-ghost btn-small"
            disabled={busy}
            onClick={(event) => {
              stopPropagation(event);
              onUndo(id);
            }}
          >
            {t("undo")}
          </button>
        </div>
      </div>
    );
  }

  return (
    <div {...cardRole}>
      <div className="suggestion-head">
        <span className={`kind-badge kind-${kind}`}>{t(kindKey(kind))}</span>
        <span className="suggestion-state">
          {t(suggestionStatusKey(status))}
        </span>
      </div>
      <p className="suggestion-diff">
        <span className="suggestion-original">{original}</span>
        <span className="suggestion-arrow" aria-hidden="true">
          →
        </span>
        <span className="suggestion-replacement">{replacement}</span>
      </p>
      <p className="suggestion-explanation">{explanation}</p>
      <div className="suggestion-actions">
        {status === "pending" ? (
          <>
            <button
              type="button"
              className="btn btn-success btn-small"
              disabled={busy}
              onClick={(event) => {
                stopPropagation(event);
                onAccept(id);
              }}
            >
              {t("accept")}
            </button>
            <button
              type="button"
              className="btn btn-danger btn-small"
              disabled={busy}
              onClick={(event) => {
                stopPropagation(event);
                onReject(id);
              }}
            >
              {t("reject")}
            </button>
          </>
        ) : (
          <button
            type="button"
            className="btn btn-ghost btn-small"
            disabled={busy}
            onClick={(event) => {
              stopPropagation(event);
              onUndo(id);
            }}
          >
            {t("undo")}
          </button>
        )}
        {manual && onDelete && (
          <button
            type="button"
            className="btn btn-ghost btn-small"
            title={t("deleteMark")}
            disabled={busy}
            onClick={(event) => {
              stopPropagation(event);
              onDelete(id);
            }}
          >
            {t("deleteMark")}
          </button>
        )}
      </div>
    </div>
  );
}
