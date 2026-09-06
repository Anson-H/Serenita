import {
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
  type KeyboardEvent,
  type ReactNode
} from "react";
import {
  type ReportEditableField
} from "../../api/client";
import { DateTimePicker } from "../../components/DateTimePicker";
import { useStatusNotification } from "../../components/StatusNotificationCenter";
import type { ScrollPositionSnapshot } from "../../utils/inputMethod";
import {
  captureScrollPosition,
  focusWithoutScroll,
  isImeComposing,
  restoreScrollPosition,
  syncCommittedText
} from "../../utils/inputMethod";
import { localIsoString } from "../../utils/localTime";
import {
  reportDateTimeInputValue
} from "./reportPresentation";
import type { ReportWorkspaceState } from "./useReportWorkspace";

export type InlineInputKind = "text" | "textarea" | "datetime-local";

type InlineEditableValueProps = {
  className?: string;
  displayValue?: ReactNode;
  field: ReportEditableField;
  inputKind?: InlineInputKind;
  itemId?: string;
  label: string;
  required?: boolean;
  value?: string | null;
  workspace: ReportInlineFieldWorkspace;
};

function inputValue(value: string | null | undefined, kind: InlineInputKind) {
  if (!value) {
    return "";
  }
  return kind === "datetime-local" ? reportDateTimeInputValue(value) : value;
}

function storedValue(value: string, kind: InlineInputKind) {
  if (kind !== "datetime-local" || !value) {
    return value || null;
  }
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? value : localIsoString(parsed);
}

export function InlineEditableValue({
  className,
  displayValue,
  field,
  inputKind = "text",
  itemId,
  label,
  required = false,
  value,
  workspace
}: InlineEditableValueProps) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(inputValue(value, inputKind));
  const [saveError, setSaveError] = useState("");
  const editorRef = useRef<HTMLInputElement | HTMLTextAreaElement | null>(null);
  const triggerRef = useRef<HTMLButtonElement | null>(null);
  const scrollSnapshotRef = useRef<ScrollPositionSnapshot | null>(null);
  const restoreTriggerFocusRef = useRef(false);

  useStatusNotification(saveError, {
    id: `report-field-${field}-${itemId ?? "report"}-error`,
    title: `${label}未保存`,
    tone: "error"
  });

  useEffect(() => {
    setDraft(inputValue(value, inputKind));
    setEditing(false);
    setSaveError("");
  }, [field, inputKind, itemId, value]);

  useLayoutEffect(() => {
    if (!editing) {
      if (!restoreTriggerFocusRef.current) return;
      restoreTriggerFocusRef.current = false;
      const frame = window.requestAnimationFrame(() => focusWithoutScroll(triggerRef.current));
      return () => window.cancelAnimationFrame(frame);
    }
    if (inputKind !== "datetime-local") focusWithoutScroll(editorRef.current);
    restoreScrollPosition(scrollSnapshotRef.current);
    scrollSnapshotRef.current = null;
  }, [editing, inputKind]);

  async function save(nextDraft = draft) {
    if (required && !nextDraft.trim()) {
      setSaveError("此项不能为空。");
      return;
    }
    if (workspace.saving) {
      return;
    }
    if (nextDraft === inputValue(value, inputKind)) {
      workspace.clearActionFeedback();
      setSaveError("");
      setEditing(false);
      return;
    }
    setSaveError("");
    const response = await workspace.updateSelectedReportField({
      field,
      item_id: itemId,
      value: storedValue(nextDraft, inputKind)
    });
    if (response) {
      setEditing(false);
    } else {
      setSaveError("保存失败，请检查后重试。");
    }
  }

  function cancel() {
    restoreTriggerFocusRef.current = true;
    setDraft(inputValue(value, inputKind));
    setSaveError("");
    setEditing(false);
  }

  function handleKeyDown(event: KeyboardEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) {
    if (isImeComposing(event)) {
      return;
    }
    if (event.key === "Escape") {
      event.preventDefault();
      cancel();
      return;
    }
    if (event.key === "Enter" && (inputKind !== "textarea" || event.metaKey || event.ctrlKey)) {
      event.preventDefault();
      restoreTriggerFocusRef.current = true;
      void save(event.currentTarget.value);
    }
  }

  if (editing && inputKind === "datetime-local") {
    return (
      <DateTimePicker
        ariaLabel={label}
        disabled={!workspace.canEdit || workspace.saving}
        mode="date-time"
        onCancel={cancel}
        onChange={setDraft}
        onCommit={(nextDraft, reason) => {
          restoreTriggerFocusRef.current = reason === "done";
          void save(nextDraft);
        }}
        value={draft}
      />
    );
  }

  if (editing && inputKind === "text") {
    return (
      <span data-field-editing="true" className={`report-inline-edit ${className ?? ""}`}>
        <input
          aria-label={label}
          autoComplete="off"
          onBlur={(event) => void save(event.currentTarget.value)}
          onChange={(event) => setDraft(event.target.value)}
          onCompositionEnd={(event) => syncCommittedText(event, setDraft)}
          onKeyDown={handleKeyDown}
          ref={(node) => { editorRef.current = node; }}
          required={required}
          type="text"
          value={draft}
        />
      </span>
    );
  }

  if (editing) {
    return (
      <span
        data-field-editing="true"
        className={`report-inline-edit report-content-sized-editor ${className ?? ""}`}
      >
        <span
          aria-hidden="true"
          className={`report-inline-edit-trigger report-inline-edit-size-mirror ${className ?? ""}`}
        >
          <span>{draft ? `${draft}\u200b` : "未记录"}</span>
        </span>
        <textarea
          aria-label={label}
          onBlur={(event) => void save(event.currentTarget.value)}
          onChange={(event) => setDraft(event.target.value)}
          onCompositionEnd={(event) => syncCommittedText(event, setDraft)}
          onKeyDown={handleKeyDown}
          ref={(node) => { editorRef.current = node; }}
          required={required}
          rows={1}
          value={draft}
        />
      </span>
    );
  }

  const empty = value === null || value === undefined || value === "";
  return (
    <button
      aria-label={workspace.canEdit ? `修改${label}` : label}
      disabled={!workspace.canEdit}
      className={`report-inline-edit-trigger ${className ?? ""}`}
      data-empty={empty ? "true" : undefined}
      data-input-kind={inputKind}
      data-interaction-owner="row"
      onClick={(event) => {
        scrollSnapshotRef.current = captureScrollPosition(
          event.currentTarget.closest<HTMLElement>(".report-detail-scroll")
        );
        workspace.clearActionFeedback();
        setSaveError("");
        setEditing(true);
      }}
      ref={triggerRef}
      type="button"
    >
      <span>{displayValue ?? value ?? "未记录"}</span>
    </button>
  );
}

type ReportInlineFieldWorkspace = Pick<ReportWorkspaceState, "canEdit" | "clearActionFeedback" | "saving" | "updateSelectedReportField">;
