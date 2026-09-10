import {useResourceDraft} from "../../utils/useResourceDraft";
import {
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
  const [saveError, setSaveError] = useState("");
  const editorRef = useRef<HTMLInputElement | HTMLTextAreaElement | null>(null);
  const triggerRef = useRef<HTMLButtonElement | null>(null);
  const scrollSnapshotRef = useRef<ScrollPositionSnapshot | null>(null);
  const restoreTriggerFocusRef = useRef(false);

  const draftState = useResourceDraft({
    resourceKey: `${workspace.reportSaveKey}:${field}:${itemId ?? ''}`,
    server: inputValue(value, inputKind), editing,
    validate: next => required && !next.trim() ? '此项不能为空。' : '',
    save: async next => {
      if (!workspace.canEdit) throw new Error('当前权限无法保存，草稿已保留。');
      const result = await workspace.updateSelectedReportField({field, item_id: itemId, value: storedValue(next, inputKind)});
      if (!result) throw new Error('保存失败，草稿已保留，请重试。');
      return next;
    }
  });
  const {draft, update: setDraft} = draftState;

  useStatusNotification(saveError || draftState.error, {
    id: `report-field-${field}-${itemId ?? "report"}-error`,
    title: `${label}未保存`,
    tone: "error"
  });

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
    setDraft(nextDraft);
    setSaveError('');
    const revision = draftState.controller.snapshot().revision;
    if (await draftState.flush()) {
      if (revision === draftState.controller.snapshot().revision) setEditing(false);
    }
  }

  function cancel() {
    if (draftState.controller.snapshot().pending) return;
    draftState.controller.cancel();
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
        disabled={!workspace.canEdit}
        mode="date-time"
        emptyOptionLabel={required ? undefined : "未知"}
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
          onCompositionStart={() => draftState.controller.composition(true)}
          onCompositionEnd={(event) => {syncCommittedText(event, setDraft); draftState.controller.composition(false);}}
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
          onCompositionStart={() => draftState.controller.composition(true)}
          onCompositionEnd={(event) => {syncCommittedText(event, setDraft); draftState.controller.composition(false);}}
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
      aria-label={workspace.canEdit ? `编辑${label}` : label}
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

type ReportInlineFieldWorkspace = Pick<ReportWorkspaceState, "reportSaveKey" | "canEdit" | "clearActionFeedback" | "saving" | "updateSelectedReportField">;
