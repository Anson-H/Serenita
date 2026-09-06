import {
  useEffect,
  useRef,
  useState,
  type FormEvent,
  type RefObject
} from "react";
import { createPortal } from "react-dom";
import {
  LAB_FLAG_TEXTS,
  apiClient,
  type LabFlagText,
  type LabTestResult,
  type ReportDetail
} from "../../api/client";
import type { LabDictionaryResponse } from "../../api/labDictionaryApi";
import { GroupedList } from "../../components/GroupedList";
import {
  PlusIcon,
  TrashIcon,
  XIcon
} from "../../components/icons";
import { SelectPopover } from "../../components/SelectPopover";
import { useStatusNotification } from "../../components/StatusNotificationCenter";
import { useModalDialog } from "../../components/useModalDialog";
import {
  isImeComposing,
  syncCommittedText
} from "../../utils/inputMethod";
import type { ReportWorkspaceState } from "./useReportWorkspace";

function labItemDisplayName(result: LabTestResult) {
  return result.item_name_zh.trim() || "未命名指标";
}

export function LabResults({
  addTriggerRef,
  adding,
  onAddingChange,
  report,
  workspace
}: {
  addTriggerRef: RefObject<HTMLButtonElement | null>;
  adding: boolean;
  onAddingChange: (adding: boolean) => void;
  report: ReportDetail;
  workspace: ReportLabResultsWorkspace;
}) {
  const results = report.lab_test_results ?? [];
  const [dictionary, setDictionary] = useState<LabDictionaryResponse | null>(null);
  const [dictionaryLoading, setDictionaryLoading] = useState(false);
  const [draftItemId, setDraftItemId] = useState("");
  const [draftResult, setDraftResult] = useState("");
  const [draftReference, setDraftReference] = useState("");
  const [draftFlag, setDraftFlag] = useState<LabFlagText>("未标记");
  const [formError, setFormError] = useState("");
  const [editingItemId, setEditingItemId] = useState<string | null>(null);
  const [editResultDraft, setEditResultDraft] = useState("");
  const [editReferenceDraft, setEditReferenceDraft] = useState("");
  const [editFlagDraft, setEditFlagDraft] = useState<LabFlagText>("未标记");
  const [editError, setEditError] = useState("");
  const addDialogRef = useRef<HTMLFormElement | null>(null);
  const addSubmittingRef = useRef(false);
  const editDialogRef = useRef<HTMLElement | null>(null);
  const editResultInputRef = useRef<HTMLInputElement | null>(null);
  const editReturnFocusRef = useRef<HTMLTableRowElement | null>(null);
  const editBusyRef = useRef(false);
  const editingResult = results.find((result) => result.item_id === editingItemId) ?? null;
  const reportCategory = results[0]?.category_name ?? report.report_name;
  const existingItemIds = new Set(results.map((result) => result.item_id));
  const availableItems = (dictionary?.items ?? []).filter(
    (item) => item.primary_category_name === reportCategory && !existingItemIds.has(item.item_id)
  );
  const mutationBusy = !workspace.canEdit || Boolean(workspace.labItemMutation) || workspace.saving;
  addSubmittingRef.current = workspace.labItemMutation === "adding";
  editBusyRef.current = mutationBusy;

  useModalDialog({
    active: adding,
    dialogRef: addDialogRef,
    escapeDisabled: addSubmittingRef.current,
    onEscape: cancelAdd,
    restoreFocusRef: addTriggerRef
  });
  useModalDialog({
    active: Boolean(editingResult),
    dialogRef: editDialogRef,
    escapeDisabled: editBusyRef.current,
    initialFocusRef: editResultInputRef,
    onEscape: closeEdit,
    restoreFocusRef: editReturnFocusRef
  });

  useStatusNotification(formError, {
    id: `report-lab-add-${report.report_id}-error`,
    title: "指标未添加",
    tone: "error"
  });

  useStatusNotification(editError, {
    id: `report-lab-edit-${report.report_id}-${editingItemId ?? "closed"}-error`,
    title: "检验结果未保存",
    tone: "error"
  });

  useEffect(() => {
    onAddingChange(false);
    setDictionary(null);
    setDraftItemId("");
    setDraftResult("");
    setDraftReference("");
    setDraftFlag("未标记");
    setFormError("");
    setEditingItemId(null);
    setEditError("");
  }, [onAddingChange, report.report_id]);

  useEffect(() => {
    if (!editingResult) return;
    setEditResultDraft(editingResult.result_text);
    setEditReferenceDraft(editingResult.reference_text ?? "");
    setEditFlagDraft(editingResult.flag_text);
    setEditError("");
  }, [
    editingResult?.flag_text,
    editingResult?.item_id,
    editingResult?.reference_text,
    editingResult?.result_text
  ]);

  useEffect(() => {
    if (!adding) return;
    let cancelled = false;
    setDictionaryLoading(true);
    setDictionary(null);
    setDraftItemId("");
    setFormError("");
    void apiClient.fetchMemberLabDictionary(workspace.memberId)
      .then((response) => {
        if (cancelled) return;
        setDictionary(response);
        const firstAvailable = response.items.find(
          (item) => item.primary_category_name === reportCategory && !existingItemIds.has(item.item_id)
        );
        setDraftItemId(firstAvailable?.item_id ?? "");
      })
      .catch((error) => {
        if (!cancelled) {
          setFormError(error instanceof Error ? error.message : "检验指标目录加载失败。");
        }
      })
      .finally(() => { if (!cancelled) setDictionaryLoading(false); });
    return () => { cancelled = true; };
  }, [adding, report.report_id, reportCategory]);

  function cancelAdd() {
    onAddingChange(false);
    setFormError("");
    setDraftResult("");
    setDraftReference("");
    setDraftFlag("未标记");
  }

  function openEdit(result: LabTestResult, trigger: HTMLTableRowElement) {
    if (mutationBusy || adding) return;
    workspace.clearActionFeedback();
    editReturnFocusRef.current = trigger;
    setEditResultDraft(result.result_text);
    setEditReferenceDraft(result.reference_text ?? "");
    setEditFlagDraft(result.flag_text);
    setEditError("");
    setEditingItemId(result.item_id);
  }

  function closeEdit() {
    setEditingItemId(null);
    setEditError("");
  }

  async function saveEditResult(nextResult = editResultDraft, nextFlag = editFlagDraft) {
    if (!editingResult || mutationBusy) return;
    if (!nextResult.trim()) {
      setEditError("结果不能为空。");
      return;
    }
    setEditError("");
    if (nextResult !== editingResult.result_text) {
      const updated = await workspace.updateSelectedReportField({
        field: "lab_result",
        item_id: editingResult.item_id,
        value: nextResult
      });
      if (!updated) {
        setEditError("保存失败，请检查后重试。");
        return;
      }
    }
    if (nextFlag !== editingResult.flag_text) {
      const updated = await workspace.updateSelectedReportField({
        field: "lab_flag",
        item_id: editingResult.item_id,
        value: nextFlag
      });
      if (!updated) setEditError("保存失败，请检查后重试。");
    }
  }

  async function saveEditReference(nextReference = editReferenceDraft) {
    if (!editingResult || mutationBusy) return;
    const nextValue = nextReference || null;
    if (nextValue === (editingResult.reference_text ?? null)) return;
    setEditError("");
    const updated = await workspace.updateSelectedReportField({
      field: "lab_reference",
      item_id: editingResult.item_id,
      value: nextValue
    });
    if (!updated) setEditError("保存失败，请检查后重试。");
  }

  async function deleteEditingResult() {
    if (!editingResult) return;
    const deleted = await workspace.deleteSelectedReportLabItem(editingResult.item_id);
    if (deleted) closeEdit();
  }

  async function submitAdd(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!draftItemId) {
      setFormError("请选择要添加的检验指标。");
      return;
    }
    if (!draftResult.trim()) {
      setFormError("请填写检验结果。");
      return;
    }
    setFormError("");
    const updated = await workspace.addSelectedReportLabItem({
      item_id: draftItemId,
      result_text: draftResult.trim(),
      reference_text: draftReference.trim() || null,
      flag_text: draftFlag
    });
    if (updated) cancelAdd();
  }

  const addEditor = adding && typeof document !== "undefined" ? createPortal(
    <div
      className="report-lab-add-backdrop dialog-viewport-backdrop"
      onMouseDown={(event) => {
        if (event.currentTarget === event.target && workspace.labItemMutation !== "adding") cancelAdd();
      }}
    >
      <form
        aria-describedby="report-lab-add-description"
        aria-labelledby="report-lab-add-title"
        aria-modal="true"
        className="report-lab-add-dialog dialog-viewport-surface dialog-title-ellipsis"
        onSubmit={submitAdd}
        ref={addDialogRef}
        role="dialog"
        tabIndex={-1}
      >
        <header className="dialog-titlebar report-lab-add-heading">
          <strong data-modal-initial-focus id="report-lab-add-title" tabIndex={-1}>添加检验指标</strong>
          <button aria-label="关闭添加检验指标弹窗" className="control control--titlebar control--icon control--ghost report-lab-add-close titlebar-icon-control" disabled={workspace.labItemMutation === "adding"} onClick={cancelAdd} type="button"><XIcon /></button>
        </header>
        <div className="dialog-body report-lab-add-body scroll-content">
          <p className="content-description" id="report-lab-add-description">仅显示“{reportCategory}”分类中尚未录入的指标</p>
          {!dictionaryLoading && dictionary && !availableItems.length ? (
            <p className="report-lab-add-state">当前分类的指标均已在这份报告中。</p>
          ) : null}
          {!dictionaryLoading && availableItems.length ? (
            <GroupedList layout="fields" className="report-lab-add-fields" density="standard">
              <label className="field-row report-lab-add-item"><span>指标</span><SelectPopover ariaLabel="选择检验指标" disabled={mutationBusy} menuWidth="content" menuAlign="end" interactionOwner="row" onChange={setDraftItemId} options={availableItems.map((item) => ({ label: item.item_name_zh, value: item.item_id }))} value={draftItemId} /></label>
              <label className="field-row"><span>结果</span><input autoComplete="off" disabled={mutationBusy} onChange={(event) => setDraftResult(event.target.value)} onCompositionEnd={(event) => syncCommittedText(event, setDraftResult)} placeholder="数值、阴性或阳性" required value={draftResult} /></label>
              <label className="field-row"><span>参考值</span><input autoComplete="off" disabled={mutationBusy} onChange={(event) => setDraftReference(event.target.value)} onCompositionEnd={(event) => syncCommittedText(event, setDraftReference)} placeholder="可不填" value={draftReference} /></label>
              <label className="field-row"><span>标记</span><SelectPopover ariaLabel="设置新增指标结果标记" className="report-lab-add-flag" disabled={mutationBusy} menuWidth="content" menuAlign="end" interactionOwner="row" onChange={setDraftFlag} options={LAB_FLAG_TEXTS.map((flag) => ({ label: flag, value: flag }))} value={draftFlag} /></label>
            </GroupedList>
          ) : null}
        </div>
        <footer className="report-lab-add-actions dialog-action-bar">
          <button className="control control--secondary secondary-button control-primary dialog-secondary-action" disabled={mutationBusy} onClick={cancelAdd} type="button"><XIcon /><span>取消</span></button>
          <button className="control control--primary command-button creation-action-button dialog-primary-action" disabled={mutationBusy || dictionaryLoading || !availableItems.length} type="submit"><PlusIcon /><span>{dictionaryLoading ? "加载中..." : workspace.labItemMutation === "adding" ? "添加中..." : "添加检验指标"}</span></button>
        </footer>
      </form>
    </div>,
    document.body
  ) : null;

  const editEditor = editingResult && typeof document !== "undefined" ? createPortal(
    <div
      className="report-lab-edit-backdrop dialog-viewport-backdrop"
      onMouseDown={(event) => {
        if (event.currentTarget === event.target && !mutationBusy) closeEdit();
      }}
    >
      <section
        aria-labelledby="report-lab-edit-title"
        aria-modal="true"
        className="report-lab-edit-dialog dialog-viewport-surface dialog-title-ellipsis"
        ref={editDialogRef}
        role="dialog"
        tabIndex={-1}
      >
        <header className="dialog-titlebar report-lab-edit-heading">
          <strong id="report-lab-edit-title">{labItemDisplayName(editingResult)}</strong>
          <button aria-label="关闭检验指标记录弹窗" className="control control--titlebar control--icon control--ghost report-lab-edit-close titlebar-icon-control" disabled={mutationBusy} onClick={closeEdit} type="button"><XIcon /></button>
        </header>
        <div className="dialog-body report-lab-edit-body scroll-content">
          <GroupedList layout="fields" className="report-lab-edit-fields" density="standard">
            <label className="field-row">
              <span>结果</span>
              <input
                aria-label="检验结果"
                autoComplete="off"
                disabled={mutationBusy}
                onBlur={(event) => void saveEditResult(event.currentTarget.value, editFlagDraft)}
                onChange={(event) => setEditResultDraft(event.target.value)}
                onCompositionEnd={(event) => syncCommittedText(event, setEditResultDraft)}
                onKeyDown={(event) => {
                  if (isImeComposing(event)) return;
                  if (event.key === "Enter") {
                    event.preventDefault();
                    event.currentTarget.blur();
                  }
                }}
                placeholder="数值、阴性或阳性"
                ref={editResultInputRef}
                required
                value={editResultDraft}
              />
            </label>
            <label className="field-row">
              <span>参考值</span>
              <input
                aria-label="检验参考值"
                autoComplete="off"
                disabled={mutationBusy}
                onBlur={(event) => void saveEditReference(event.currentTarget.value)}
                onChange={(event) => setEditReferenceDraft(event.target.value)}
                onCompositionEnd={(event) => syncCommittedText(event, setEditReferenceDraft)}
                onKeyDown={(event) => {
                  if (isImeComposing(event)) return;
                  if (event.key === "Enter") {
                    event.preventDefault();
                    event.currentTarget.blur();
                  }
                }}
                placeholder="未记录"
                value={editReferenceDraft}
              />
            </label>
            <label className="field-row">
              <span>指标状态</span>
              <SelectPopover
                ariaLabel="设置指标状态"
                className="report-lab-flag-picker"
                disabled={mutationBusy}
                menuWidth="content" menuAlign="end" interactionOwner="row"
                onChange={(nextFlag) => {
                  setEditFlagDraft(nextFlag);
                  void saveEditResult(editResultDraft, nextFlag);
                }}
                options={LAB_FLAG_TEXTS.map((flag) => ({ label: flag, value: flag }))}
                value={editFlagDraft}
              />
            </label>
          </GroupedList>
          <button
            aria-label={`删除检验指标记录：${labItemDisplayName(editingResult)}`}
            className="control control--secondary control--danger report-lab-edit-delete removal-action-control"
            disabled={results.length <= 1 || mutationBusy}
            onClick={() => void deleteEditingResult()}
            onMouseDown={(event) => event.preventDefault()}
            title={results.length <= 1 ? "检验报告至少保留一条记录；如需移除，请删除整份报告" : `删除${labItemDisplayName(editingResult)}记录`}
            type="button"
          >
            <TrashIcon className="message-action-icon" />
            <span>删除检验指标记录</span>
          </button>
        </div>
      </section>
    </div>,
    document.body
  ) : null;

  if (!results.length) {
    return <><div className="report-subtle-empty"><strong>暂无检验结果</strong><p>当前报告缺少可展示的结构化检验结果。</p></div>{addEditor}{editEditor}</>;
  }
  const row = (result: LabTestResult) => (
    <tr
      aria-label={`修改检验指标记录：${labItemDisplayName(result)}`}
      data-active={editingItemId === result.item_id ? "true" : undefined}
      data-flag={result.flag_text}
      key={result.item_id}
      onClick={(event) => openEdit(result, event.currentTarget)}
      onKeyDown={(event) => {
        if (isImeComposing(event) || (event.key !== "Enter" && event.key !== " ")) return;
        event.preventDefault();
        openEdit(result, event.currentTarget);
      }}
      tabIndex={mutationBusy || adding ? -1 : 0}
    >
      <th data-label="指标" scope="row"><span className="report-lab-canonical-name">{labItemDisplayName(result)}</span></th>
      <td data-label="结果">{result.result_text}</td>
      <td data-label="参考值">{result.reference_text || "未记录"}</td>
    </tr>
  );
  return (
    <>
      {addEditor}
      {editEditor}
      <div className="lab-table-scroll">
        <table className="lab-results-table structured-data-grid interactive-data-grid">
          <thead><tr><th scope="col">指标</th><th scope="col">结果</th><th scope="col">参考值</th></tr></thead>
          <tbody>{results.map((result) => row(result))}</tbody>
        </table>
        <button
          className="control control--row report-lab-add-row grouped-list-create-button"
          disabled={mutationBusy || adding}
          onClick={() => {
            workspace.clearActionFeedback();
            onAddingChange(true);
          }}
          ref={addTriggerRef}
          type="button"
        >
          <PlusIcon className="settings-action-icon" />
          <span>添加检验指标</span>
        </button>
      </div>
    </>
  );
}

type ReportLabResultsWorkspace = Pick<ReportWorkspaceState, "addSelectedReportLabItem" | "canEdit" | "clearActionFeedback" | "deleteSelectedReportLabItem" | "labItemMutation" | "memberId" | "saving" | "updateSelectedReportField">;
