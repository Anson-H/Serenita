import {
  useEffect,
  useRef,
  useState,
  type KeyboardEvent
} from "react";
import { createPortal } from "react-dom";
import {
  type LabDictionaryCategory
} from "../../api/client";
import { GroupedList } from "../../components/GroupedList";
import { MergeIcon, PlusIcon, XIcon } from "../../components/icons";
import { SelectPopover } from "../../components/SelectPopover";
import { useModalDialog } from "../../components/useModalDialog";
import {
  formTextValue,
  isImeComposing,
  keepTextControlFocused,
  syncCommittedText
} from "../../utils/inputMethod";
import type { CreateDialogState, PendingMergeConfirmation } from "./labDictionaryDrafts";

export function DictionaryMergeConfirmation({
  confirmation,
  onCancel,
  saving
}: {
  confirmation: PendingMergeConfirmation;
  onCancel: () => void;
  saving: boolean;
}) {
  const dialogRef = useRef<HTMLElement | null>(null);
  useModalDialog({
    active: true,
    dialogRef,
    escapeDisabled: saving,
    onEscape: onCancel
  });
  return createPortal(
    <div
      className="dictionary-confirmation-backdrop dialog-viewport-backdrop"
      onMouseDown={(event) => {
        if (event.currentTarget === event.target && !saving) onCancel();
      }}
    >
      <section
        aria-labelledby="dictionary-confirmation-title"
        aria-modal="true"
        className="dictionary-confirmation dialog-viewport-surface dialog-title-ellipsis"
        data-kind="merge"
        ref={dialogRef}
        role="dialog"
        tabIndex={-1}
      >
        <header className="dialog-titlebar">
          <h2 data-modal-initial-focus id="dictionary-confirmation-title" tabIndex={-1}>合并指标，还是放弃修改？</h2>
          <button
            aria-label="关闭确认窗口"
            className="control control--titlebar control--icon control--ghost icon-action-control settings-icon-button titlebar-icon-control"
            disabled={saving}
            onClick={onCancel}
            type="button"
          >
            <XIcon />
          </button>
        </header>
        <div className="dialog-body dictionary-impact-ledger scroll-content">
          <strong>“{confirmation.sourceItemNameZh}”与“{confirmation.targetItemNameZh}”发生冲突</strong>
          <p>
            合并后保留“{confirmation.targetItemNameZh}”的规范名称与主分类，
            “{confirmation.sourceItemNameZh}”及其既有别名会成为目标指标的别名。
          </p>
          <p>
            将检查并迁移 {confirmation.sourceResultCount} 条来源结果；目标指标当前有
            {confirmation.targetResultCount} 条结果。未保存的其他表单修改不会写入。
          </p>
          <p>如果同一原件和就诊时间中存在不同结果，系统会阻止合并，不会覆盖报告。</p>
        </div>
        <footer className="dialog-action-bar">
          <button className="control control--secondary secondary-button control-primary dialog-secondary-action" disabled={saving} onClick={onCancel} type="button">
            <XIcon />
            <span>放弃修改</span>
          </button>
          <button
            className="control control--secondary dictionary-merge-button dialog-warning-action"
            disabled={saving}
            onClick={() => void confirmation.run()}
            type="button"
          >
            <MergeIcon />
            <span>{saving ? "正在处理..." : "合并指标"}</span>
          </button>
        </footer>
      </section>
    </div>,
    document.body
  );
}

export function DictionaryCreateDialog({
  categories,
  dialog,
  onCancel,
  onChange,
  onSubmit,
  saving
}: {
  categories: LabDictionaryCategory[];
  dialog: CreateDialogState;
  onCancel: () => void;
  onChange: (next: CreateDialogState) => void;
  onSubmit: (name: string) => Promise<void>;
  saving: boolean;
}) {
  const dialogRef = useRef<HTMLFormElement | null>(null);
  const isItem = dialog.kind === "item";
  const canSubmit = Boolean(dialog.name.trim() && (!isItem || dialog.primaryCategoryName));
  useModalDialog({
    active: true,
    dialogRef,
    escapeDisabled: saving,
    onEscape: onCancel
  });

  return createPortal(
    <div
      className="dictionary-confirmation-backdrop dialog-viewport-backdrop"
      onMouseDown={(event) => {
        if (event.currentTarget === event.target && !saving) onCancel();
      }}
    >
      <form
        aria-labelledby="dictionary-create-title"
        aria-modal="true"
        className="dictionary-confirmation dictionary-create-dialog dialog-viewport-surface dialog-title-ellipsis"
        data-kind="create"
        onSubmit={(event) => {
          event.preventDefault();
          const submittedName = formTextValue(event.currentTarget, "dictionary-name", dialog.name).trim();
          if (submittedName && (!isItem || dialog.primaryCategoryName) && !saving) {
            void onSubmit(submittedName);
          }
        }}
        ref={dialogRef}
        role="dialog"
        tabIndex={-1}
      >
        <header className="dialog-titlebar">
          <h2 data-modal-initial-focus id="dictionary-create-title" tabIndex={-1}>新增{isItem ? "指标" : "分类"}</h2>
          <button
            aria-label="关闭新建窗口"
            className="control control--titlebar control--icon control--ghost icon-action-control settings-icon-button titlebar-icon-control"
            disabled={saving}
            onClick={onCancel}
            type="button"
          >
            <XIcon />
          </button>
        </header>
        <div className="dialog-body scroll-content">
          <GroupedList layout="fields" density="standard">
            <label className="field-row">
              <span>{isItem ? "指标名称" : "分类名称"}</span>
              <input
                aria-required="true"
                maxLength={isItem ? 128 : 64}
                name="dictionary-name"
                onChange={(event) => onChange({ ...dialog, name: event.target.value })}
                onCompositionEnd={(event) => syncCommittedText(event, (name) => onChange({ ...dialog, name }))}
                placeholder={isItem ? "输入指标的规范名称" : "输入分类名称"}
                required
                value={dialog.name}
              />
            </label>
            {isItem ? (
              <div className="dictionary-create-field field-row">
                <span>主分类</span>
                <SelectPopover
                  ariaLabel="选择新增指标的主分类"
                  className="dictionary-form-picker"
                  menuWidth="content" menuAlign="end" interactionOwner="row"
                  onChange={(primaryCategoryName) => onChange({ ...dialog, primaryCategoryName })}
                  options={categories.map((category) => ({
                    label: category.category_name,
                    value: category.category_name
                  }))}
                  placeholder="选择一个主分类"
                  value={dialog.primaryCategoryName}
                />
              </div>
            ) : null}
          </GroupedList>
        </div>
        <footer className="dialog-action-bar">
          <button className="control control--secondary secondary-button control-primary dialog-secondary-action" disabled={saving} onClick={onCancel} type="button">
            <XIcon />
            <span>取消</span>
          </button>
          <button
            className="control control--primary command-button creation-action-button dialog-primary-action"
            disabled={!canSubmit || saving}
            onMouseDown={keepTextControlFocused}
            type="submit"
          >
            <PlusIcon />
            <span>{saving ? "正在添加..." : "添加"}</span>
          </button>
        </footer>
      </form>
    </div>,
    document.body
  );
}

export function AliasEditor({ aliases, onChange }: { aliases: string[]; onChange: (aliases: string[]) => void }) {
  const [draft, setDraft] = useState(() => aliases.join("、"));
  const inputRef = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    if (document.activeElement !== inputRef.current) {
      setDraft(aliases.join("、"));
    }
  }, [aliases]);

  function commit(value: string) {
    const next = Array.from(new Set(
      value
        .split(/[、，,\n]+/)
        .map((alias) => alias.trim())
        .filter(Boolean)
    ));
    setDraft(next.join("、"));
    if (JSON.stringify(next) !== JSON.stringify(aliases)) onChange(next);
  }

  function handleKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    if (isImeComposing(event)) {
      return;
    }
    if (event.key === "Enter") {
      event.preventDefault();
      event.currentTarget.blur();
    }
  }

  return (
    <input
      aria-label="指标别名"
      className="dictionary-alias-input"
      onBlur={(event) => commit(event.currentTarget.value)}
      onChange={(event) => setDraft(event.target.value)}
      onCompositionEnd={(event) => syncCommittedText(event, setDraft)}
      onKeyDown={handleKeyDown}
      placeholder="多个别名用顿号分隔"
      ref={inputRef}
      value={draft}
    />
  );
}
