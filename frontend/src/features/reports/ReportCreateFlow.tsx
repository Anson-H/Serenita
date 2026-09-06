import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type FormEvent
} from "react";
import { createPortal } from "react-dom";
import { ENTRY_FIELDS, REPORT_DETAIL_KEYS, type EntryField } from "./reportFields";

import {
  LAB_FLAG_TEXTS,
  REPORT_TYPES,
  apiClient,
  type CreateReportInput,
  type LabFlagText,
  type ReportType
} from "../../api/client";
import type { LabDictionaryResponse } from "../../api/labDictionaryApi";
import { DateTimePicker } from "../../components/DateTimePicker";
import { GroupedList, ReadonlyField } from "../../components/GroupedList";
import { CheckIcon, ChevronLeftIcon, ChevronRightIcon, TextFormatIcon, UploadIcon, XIcon } from "../../components/icons";
import { SelectPopover } from "../../components/SelectPopover";
import { useStatusNotification } from "../../components/StatusNotificationCenter";
import { useModalDialog } from "../../components/useModalDialog";
import {
  formTextValue,
  formTextValues,
  keepTextControlFocused,
  syncCommittedText
} from "../../utils/inputMethod";
import { localDateTimeInputValue, localIsoString } from "../../utils/localTime";
import { formatReportDate } from "./reportPresentation";
import type { ReportWorkspaceState } from "./useReportWorkspace";

type CreatePhase = "method" | "type" | "editor";
type DraftValues = Record<string, string>;
type LabValueDraft = { flag: LabFlagText; reference: string; result: string };

const TYPE_DESCRIPTIONS: Record<ReportType, string> = {
  "检验报告": "逐项填写检验指标、结果与参考值",
  "检查报告": "填写检查项目、所见和结论",
  "病理报告": "填写标本、巨检和病理诊断",
  "手术报告": "填写诊断、麻醉和手术经过",
  "其它报告": "填写无法归入上述类型的报告正文"
};

function initialDraft(): DraftValues {
  const now = localDateTimeInputValue(new Date());
  return {
    report_name: "",
    report_time: now,
    institution_name: "",
    ...Object.fromEntries(Object.values(ENTRY_FIELDS).flat().map(field => [field.key, ""]))
  };
}

function optionalText(value: string) {
  return value.trim() || null;
}

function requiredDateTime(value: string, label: string) {
  const parsed = new Date(value);
  if (!value || Number.isNaN(parsed.getTime())) {
    throw new Error(`请填写有效的${label}。`);
  }
  return localIsoString(parsed);
}

function optionalDateTime(value: string, label: string) {
  return value ? requiredDateTime(value, label) : null;
}

function ReportDateEntry({ field, value, onChange, disabled }: {
  field: EntryField;
  value: string;
  onChange: (value: string) => void;
  disabled: boolean;
}) {
  const [editing, setEditing] = useState(false);
  const [dateDraft, setDateDraft] = useState(value);
  const triggerRef = useRef<HTMLButtonElement | null>(null);
  function close(restoreFocus: boolean) {
    setEditing(false);
    if (restoreFocus) requestAnimationFrame(() => triggerRef.current?.focus({ preventScroll: true }));
  }
  return (
    <div className="field-row">
      <span className="field-label">{field.label} {field.required ? <b>*</b> : null}</span>
      <div className="field-value">
        {editing ? <DateTimePicker
          ariaLabel={field.label}
          disabled={disabled}
          mode="date-time"
          onCancel={() => close(true)}
          onChange={setDateDraft}
          onCommit={(nextValue, reason) => { onChange(nextValue); close(reason === "done"); }}
          value={dateDraft}
        /> : <button
          aria-label={field.label}
          className="report-inline-edit-trigger"
          data-interaction-owner="row"
          disabled={disabled}
          onClick={() => { setDateDraft(value || localDateTimeInputValue(new Date())); setEditing(true); }}
          ref={triggerRef}
          type="button"
        ><span>{value ? <time dateTime={value}>{formatReportDate(value, true)}</time> : "未记录"}</span></button>}
      </div>
    </div>
  );
}

function ChoiceRow({
  description,
  disabled = false,
  icon,
  label,
  onClick
}: {
  description: string;
  disabled?: boolean;
  icon: "text" | "upload";
  label: string;
  onClick: () => void;
}) {
  return (
    <button className="report-create-choice grouped-list-wrapping-navigation-row" disabled={disabled} onClick={onClick} type="button">
      <span className="report-create-choice-icon">
        {icon === "text" ? <TextFormatIcon /> : <UploadIcon />}
      </span>
      <span className="report-create-choice-copy"><strong>{label}</strong><small>{description}</small></span>
      <ChevronRightIcon className="report-create-choice-arrow" />
    </button>
  );
}

export function ReportCreateFlow({
  onClose,
  onRequestUpload,
  open,
  workspace
}: {
  onClose: () => void;
  onRequestUpload: () => void;
  open: boolean;
  workspace: ReportWorkspaceState;
}) {
  const dialogRef = useRef<HTMLElement | null>(null);
  const [phase, setPhase] = useState<CreatePhase>("method");
  const [selectedType, setSelectedType] = useState<ReportType | null>(null);
  const [draft, setDraft] = useState<DraftValues>(() => initialDraft());
  const [dictionary, setDictionary] = useState<LabDictionaryResponse | null>(null);
  const [dictionaryLoading, setDictionaryLoading] = useState(false);
  const [labCategory, setLabCategory] = useState("");
  const [labValues, setLabValues] = useState<Record<string, LabValueDraft>>({});
  const [error, setError] = useState("");

  useStatusNotification(error, {
    id: "report-create-error",
    title: "报告未保存",
    tone: "error"
  });

  useModalDialog({
    active: open,
    dialogRef,
    escapeDisabled: workspace.creating,
    focusKey: phase,
    onEscape: () => {
      if (phase === "editor") {
        setPhase("type");
        setSelectedType(null);
      } else if (phase === "type") {
        setPhase("method");
      } else {
        onClose();
      }
    }
  });

  useEffect(() => {
    if (!open) return;
    setPhase("method");
    setSelectedType(null);
    setDraft(initialDraft());
    setLabCategory("");
    setLabValues({});
    setError("");
  }, [open]);

  useEffect(() => {
    if (!open || phase !== "editor" || selectedType !== "检验报告" || dictionary) return;
    let cancelled = false;
    setDictionaryLoading(true);
    void apiClient.fetchMemberLabDictionary(workspace.memberId)
      .then((response) => {
        if (cancelled) return;
        const initialCategory = response.categories[0]?.category_name ?? "";
        setDictionary(response);
        setLabCategory(initialCategory);
        setDraft((current) => current.report_name.trim()
          ? current
          : { ...current, report_name: initialCategory });
      })
      .catch((loadError) => {
        if (!cancelled) setError(loadError instanceof Error ? loadError.message : "检验指标目录加载失败。");
      })
      .finally(() => { if (!cancelled) setDictionaryLoading(false); });
    return () => { cancelled = true; };
  }, [dictionary, open, phase, selectedType]);

  const labItems = useMemo(
    () => (dictionary?.items ?? []).filter((item) => item.primary_category_name === labCategory),
    [dictionary, labCategory]
  );

  useEffect(() => {
    if (
      !open
      || phase !== "editor"
      || selectedType !== "检验报告"
      || !dictionary
      || labCategory
    ) return;
    const initialCategory = dictionary.categories[0]?.category_name ?? "";
    setLabCategory(initialCategory);
    setDraft((current) => current.report_name.trim()
      ? current
      : { ...current, report_name: initialCategory });
  }, [dictionary, labCategory, open, phase, selectedType]);

  function updateDraft(key: string, value: string) {
    setDraft((current) => ({ ...current, [key]: value }));
  }

  function updateLabValue<Key extends keyof LabValueDraft>(
    itemId: string,
    key: Key,
    value: LabValueDraft[Key]
  ) {
    setLabValues((current) => ({
      ...current,
      [itemId]: {
        flag: current[itemId]?.flag ?? "未标记",
        reference: current[itemId]?.reference ?? "",
        result: current[itemId]?.result ?? "",
        [key]: value
      }
    }));
  }

  function buildPayload(
    submittedDraft: DraftValues = draft,
    submittedLabValues: Record<string, LabValueDraft> = labValues
  ): CreateReportInput {
    if (!selectedType) throw new Error("请选择报告类型。");
    const reportTime = requiredDateTime(submittedDraft.report_time, "就诊时间");
    const reportName = selectedType === "检验报告"
      ? labCategory
      : submittedDraft.report_name.trim();
    if (!reportName) {
      throw new Error(selectedType === "检验报告" ? "请选择报告名称。" : "请填写报告名称。");
    }
    const common = {
      report_type: selectedType,
      report_name: reportName,
      report_time: reportTime,
      institution_name: optionalText(submittedDraft.institution_name)
    } satisfies CreateReportInput;

    if (selectedType === "检验报告") {
      const results = labItems.flatMap((item) => {
        const value = submittedLabValues[item.item_id];
        if (!value?.result.trim()) return [];
        return [{
          item_id: item.item_id,
          item_name_zh: item.item_name_zh,
          aliases: item.aliases,
          category_name: labCategory,
          result_text: value.result.trim(),
          reference_text: optionalText(value.reference),
          flag_text: value.flag
        }];
      });
      if (!results.length) throw new Error("请至少填写一项检验结果。");
      return { ...common, lab_test_results: results };
    }
    const values = Object.fromEntries((ENTRY_FIELDS[selectedType] ?? []).map(field => {
      const raw = submittedDraft[field.key] ?? "";
      if (field.required && !raw.trim()) throw new Error(`请填写${field.label}。`);
      return [field.key, field.type === "datetime-local" ? optionalDateTime(raw, field.label) : optionalText(raw)];
    }));
    return { ...common, [REPORT_DETAIL_KEYS[selectedType]]: values };

  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    try {
      const submittedDraft = formTextValues(event.currentTarget, draft);
      const submittedLabValues = Object.fromEntries(labItems.map((item) => {
        const fallback = labValues[item.item_id] ?? { flag: "未标记", reference: "", result: "" };
        return [item.item_id, {
          ...fallback,
          reference: formTextValue(event.currentTarget, `lab-${item.item_id}-reference`, fallback.reference),
          result: formTextValue(event.currentTarget, `lab-${item.item_id}-result`, fallback.result)
        }];
      }));
      const created = await workspace.createManualReport(buildPayload(submittedDraft, submittedLabValues));
      if (created) onClose();
      else setError("报告未能保存，请检查后重试。");
    } catch (submitError) {
      setError(submitError instanceof Error ? submitError.message : "报告未能保存。");
    }
  }

  if (!open || typeof document === "undefined") return null;

  const dialogDescription = phase === "method" ? "报告库" : phase === "type" ? "文字录入" : selectedType;
  const header = (
    <header className="dialog-titlebar report-create-header">
      <h2 data-modal-initial-focus id="report-create-title" tabIndex={-1}>
        {phase === "method" ? "新增报告" : phase === "type" ? "选择报告类型" : "填写报告信息"}
      </h2>
      <button aria-label="关闭新增报告" className="control control--titlebar control--icon control--ghost report-create-close titlebar-icon-control" onClick={onClose} type="button"><XIcon /></button>
    </header>
  );

  return createPortal(
    <div className="report-create-backdrop dialog-viewport-backdrop" onMouseDown={(event) => { if (event.currentTarget === event.target) onClose(); }}>
      <section
        aria-labelledby="report-create-title"
        aria-modal="true"
        className="report-create-dialog dialog-viewport-surface dialog-title-ellipsis"
        data-phase={phase}
        ref={dialogRef}
        role="dialog"
        tabIndex={-1}
      >
        {header}
        {phase === "method" ? (
          <div className="dialog-body report-create-choices scroll-content">
            <p className="content-description">{dialogDescription}</p>
            <GroupedList className="report-create-choice-list" density="standard">
              <ChoiceRow
                description="手动填写结构化报告信息，保存后仍可继续修改"
                icon="text"
                label="文字录入"
                onClick={() => setPhase("type")}
              />
              <ChoiceRow
                description={workspace.reportUploadUnavailableReason || "上传 PDF 或报告图片，由 Serenita 识别整理"}
                disabled={workspace.uploadBlocked}
                icon="upload"
                label="上传文件"
                onClick={() => { onRequestUpload(); onClose(); }}
              />
            </GroupedList>
            {workspace.attachmentCapabilitiesError ? <button type="button" className="control control--compact" onClick={workspace.retryAttachmentCapabilities}>重试附件能力</button> : null}
          </div>
        ) : null}
        {phase === "type" ? (
          <div className="report-create-type-step">
            <div className="dialog-body report-create-type-body scroll-content">
              <p className="content-description">{dialogDescription} · 选择后将显示该类型对应的录入字段。</p>
              <GroupedList className="report-create-type-list" density="standard">
                {REPORT_TYPES.map((type) => (
                  <button
                    className="grouped-list-wrapping-navigation-row"
                    key={type}
                    onClick={() => { setSelectedType(type); setPhase("editor"); setError(""); }}
                    type="button"
                  >
                    <span><strong>{type}</strong><small>{TYPE_DESCRIPTIONS[type]}</small></span>
                    <ChevronRightIcon className="report-create-choice-arrow" />
                  </button>
                ))}
              </GroupedList>
            </div>
            <footer className="report-create-footer dialog-action-bar"><button className="control control--secondary secondary-button control-primary dialog-secondary-action" onClick={() => setPhase("method")} type="button"><ChevronLeftIcon /><span>返回</span></button></footer>
          </div>
        ) : null}
        {phase === "editor" && selectedType ? (
          <form className="report-create-form" onSubmit={submit}>
            <div className="dialog-body report-create-form-scroll scroll-content">
              <p className="content-description">{dialogDescription}</p>
              <section aria-labelledby="report-create-common-heading" className="report-create-form-section">
                <h3 id="report-create-common-heading">基础信息</h3>
                <GroupedList layout="fields" className="report-create-form-grid" density="standard">
                  <ReadonlyField className="field-row" label="报告类型" value={selectedType} />
                  {selectedType === "检验报告" ? (
                    <label className="field-row">
                      <span>报告名称 <b>*</b></span>
                      <SelectPopover
                        ariaLabel="报告名称"
                        disabled={dictionaryLoading || !dictionary?.categories.length}
                        menuWidth="content" menuAlign="end" interactionOwner="row"
                        onChange={(nextCategory) => {
                          setLabCategory(nextCategory);
                          setDraft((current) => ({ ...current, report_name: nextCategory }));
                          setLabValues({});
                        }}
                        options={(dictionary?.categories ?? []).map((category) => ({
                          label: category.category_name,
                          value: category.category_name
                        }))}
                        placeholder={dictionaryLoading ? "加载中..." : "暂无分类"}
                        value={labCategory}
                      />
                    </label>
                  ) : (
                    <label className="field-row"><span>报告名称 <b>*</b></span><input autoComplete="off" name="report_name" onChange={(event) => updateDraft("report_name", event.target.value)} onCompositionEnd={(event) => syncCommittedText(event, (value) => updateDraft("report_name", value))} placeholder="例如：腹部超声" required value={draft.report_name} /></label>
                  )}
                  <label className="field-row"><span>就诊机构</span><input autoComplete="off" name="institution_name" onChange={(event) => updateDraft("institution_name", event.target.value)} onCompositionEnd={(event) => syncCommittedText(event, (value) => updateDraft("institution_name", value))} value={draft.institution_name} /></label>
                  <ReportDateEntry field={{ key: "report_time", label: "就诊时间", required: true }} value={draft.report_time} onChange={(value) => updateDraft("report_time", value)} disabled={workspace.creating} />
                </GroupedList>
              </section>

              {selectedType === "检验报告" ? (
                <section aria-labelledby="report-create-lab-heading" className="report-create-form-section report-create-lab-section">
                  <div className="report-create-form-section-heading"><h3 id="report-create-lab-heading">检验结果</h3><small>只保存已填写结果的指标</small></div>
                  {!dictionaryLoading && dictionary ? (
                    <>
                      {labItems.length ? (
                        <div className="report-create-lab-table" role="group" aria-label={`${labCategory}指标`}>
                          <div className="report-create-lab-head"><span>指标</span><span>结果</span><span>参考值</span><span>标记</span></div>
                          {labItems.map((item) => {
                            const value = labValues[item.item_id] ?? { flag: "未标记", reference: "", result: "" };
                            return (
                              <div className="report-create-lab-row" key={item.item_id}>
                                <strong><span className="report-create-lab-mobile-label">指标</span><span>{item.item_name_zh}</span></strong>
                                <label><span className="report-create-lab-mobile-label">结果</span><input aria-label={`${item.item_name_zh}结果`} name={`lab-${item.item_id}-result`} onChange={(event) => updateLabValue(item.item_id, "result", event.target.value)} onCompositionEnd={(event) => syncCommittedText(event, (nextValue) => updateLabValue(item.item_id, "result", nextValue))} placeholder="数值、阴性或阳性" value={value.result} /></label>
                                <label><span className="report-create-lab-mobile-label">参考值</span><input aria-label={`${item.item_name_zh}参考值`} name={`lab-${item.item_id}-reference`} onChange={(event) => updateLabValue(item.item_id, "reference", event.target.value)} onCompositionEnd={(event) => syncCommittedText(event, (nextValue) => updateLabValue(item.item_id, "reference", nextValue))} value={value.reference} /></label>
                                <label><span className="report-create-lab-mobile-label">标记</span><SelectPopover ariaLabel={`${item.item_name_zh}结果标记`} className="report-create-lab-flag-picker" menuWidth="trigger" menuAlign="start" interactionOwner="self" onChange={(flag) => updateLabValue(item.item_id, "flag", flag)} options={LAB_FLAG_TEXTS.map((flag) => ({ label: flag, value: flag }))} value={value.flag} /></label>
                              </div>
                            );
                          })}
                        </div>
                      ) : <p className="report-create-status">该分类还没有可录入的指标，请先在检验指标目录中维护指标。</p>}
                    </>
                  ) : null}
                </section>
              ) : (
                <section aria-labelledby="report-create-typed-heading" className="report-create-form-section">
                  <h3 id="report-create-typed-heading">{selectedType === "检查报告" ? "检查结果" : selectedType === "病理报告" ? "病理结果" : selectedType === "手术报告" ? "手术记录" : "报告内容"}</h3>
                  {selectedType === "其它报告" ? (
                    <textarea
                      aria-labelledby="report-create-typed-heading"
                      className="report-create-body-input"
                      name="report_body"
                      onChange={(event) => updateDraft("report_body", event.target.value)}
                      onCompositionEnd={(event) => syncCommittedText(event, (value) => updateDraft("report_body", value))}
                      placeholder="录入报告正文"
                      required
                      rows={6}
                      value={draft.report_body}
                    />
                  ) : <GroupedList layout="fields" className="report-create-form-grid report-create-structured-grid structured-definition" density="standard">
                    {(ENTRY_FIELDS[selectedType] ?? []).map((field) => (
                      field.type === "datetime-local" ? <ReportDateEntry key={field.key} field={field} value={draft[field.key]} onChange={(value) => updateDraft(field.key, value)} disabled={workspace.creating} /> : <label className="field-row" key={field.key}>
                        <span>{field.label} {field.required ? <b>*</b> : null}</span>
                        {field.textarea ? (
                          <textarea name={field.key} onChange={(event) => updateDraft(field.key, event.target.value)} onCompositionEnd={(event) => syncCommittedText(event, (value) => updateDraft(field.key, value))} placeholder={field.placeholder} required={field.required} rows={1} value={draft[field.key]} />
                        ) : (
                          <input name={field.key} onChange={(event) => updateDraft(field.key, event.target.value)} onCompositionEnd={(event) => syncCommittedText(event, (value) => updateDraft(field.key, value))} placeholder={field.placeholder} required={field.required} type={field.type ?? "text"} value={draft[field.key]} />
                        )}
                      </label>
                    ))}
                  </GroupedList>}
                </section>
              )}
            </div>
            <footer className="report-create-footer dialog-action-bar">
              <button className="control control--secondary secondary-button control-primary dialog-secondary-action" disabled={workspace.creating} onClick={() => { setPhase("type"); setSelectedType(null); setError(""); }} type="button"><ChevronLeftIcon /><span>返回</span></button>
              <button className="control control--primary command-button creation-action-button dialog-primary-action" disabled={!workspace.canEdit || workspace.creating || dictionaryLoading} onMouseDown={keepTextControlFocused} type="submit"><CheckIcon /><span>{dictionaryLoading ? "加载中..." : workspace.creating ? "保存中..." : "保存报告"}</span></button>
            </footer>
          </form>
        ) : null}
      </section>
    </div>,
    document.body
  );
}
