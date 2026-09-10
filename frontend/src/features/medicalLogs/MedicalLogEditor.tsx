import { navigationLabels } from "../../components/navigationLabels";
import { useId, useEffect, useImperativeHandle, useLayoutEffect, useRef, type Ref } from "react";
import { createMedicalLog, updateMedicalLog, deleteMedicalLog, type MedicalLog, type MedicalLogInput, type MedicalLogChanges } from "../../api/medicalLogApi";
import { GroupedList, ReadonlyField } from "../../components/GroupedList";
import { CheckIcon, TrashIcon } from "../../components/icons";
import { WorkspaceToolbar } from "../../components/WorkspaceToolbar";
import { useStatusNotification } from "../../components/StatusNotificationCenter";
import { useAutosaveResource } from "../../utils/useAutosaveResource";
import { useActiveScope } from "../../utils/useActiveScope";
import { ContentDialog } from "../../components/ContentDialog";
import { DateField } from "../../components/DateField";
import { formatDateOnly } from "../../utils/localTime";

export type MedicalLogEditorHandle = { medicalLogId: string | undefined; remove: () => Promise<boolean> };

function emptyLog(): MedicalLogInput {
  const today = new Date();
  const recorded_on = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, "0")}-${String(today.getDate()).padStart(2, "0")}`;
  return { title: "", content: "", recorded_on };
}
export function MedicalLogEditor({ memberId, canEdit, log, readError, onSaved, onDeleted, onClose, ref }: {
  memberId: string; canEdit: boolean; log: MedicalLog | null; readError?: string;
  onSaved: (saved: MedicalLog) => void; onDeleted: () => void; onClose: () => void;
  ref?: Ref<MedicalLogEditorHandle>;
}) {
  const formId=useId();
  const persisted = useRef(log);
  const composing = useRef(false);
  const isCurrent = useActiveScope(`${memberId}:${log?.medical_log_id ?? "new"}`);
  const values = (item: MedicalLogInput): MedicalLogInput => ({ title: item.title, content: item.content, recorded_on: item.recorded_on });
  const editor = useAutosaveResource<MedicalLogInput>({
    resourceKey: `${memberId}:${log?.medical_log_id ?? "new"}`, server: values(log ?? emptyLog()), enabled: canEdit,
    isNew: !persisted.current, createMessage: "创建健康日记尚未保存，请先完成或关闭创建窗口。",
    validate: value => value.title.trim() && value.content.trim() ? "" : "请填写标题和日记内容，编辑内容尚未保存。",
    save: async value => {
      const changes = Object.fromEntries(Object.entries(value).filter(([key, entry]) => !persisted.current || JSON.stringify(persisted.current[key as keyof MedicalLogInput]) !== JSON.stringify(entry)));
      const { medical_log: saved } = persisted.current
        ? await updateMedicalLog(memberId, persisted.current.medical_log_id, changes)
        : await createMedicalLog(memberId, value);
      persisted.current = saved;
      if (isCurrent()) onSaved(saved);
      return values(saved);
    },
    onRemoved: onDeleted,
    remove: async () => { if (persisted.current) { await deleteMedicalLog(memberId, persisted.current.medical_log_id);  } },
  });
  const { draft, error, saving, deleting, dirty, flush, remove } = editor;
  function change(changes: MedicalLogChanges, immediate = false) {
    editor.change(changes);
    if (immediate && persisted.current) void flush();
  }
  const panel = useRef<HTMLElement>(null);
  const body = useRef<HTMLTextAreaElement>(null);
  useLayoutEffect(() => {
    const area = body.current;
    if (!area) return;
    const fit = () => { area.style.height = "auto"; area.style.height = `${area.scrollHeight}px`; };
    fit();
    let width = area.getBoundingClientRect().width;
    const observer = new ResizeObserver(() => {
      const nextWidth = area.getBoundingClientRect().width;
      if (nextWidth !== width) { width = nextWidth; fit(); }
    });
    observer.observe(area);
    return () => observer.disconnect();
  }, [draft.content, canEdit]);
  useStatusNotification(error, { id: "medical-log-save-error", title: "健康日记未保存", tone: "error" });

  useEffect(() => {
    if (window.matchMedia("(max-width: 650px)").matches) panel.current?.focus();
  }, []);
  useEffect(() => { if (log) persisted.current = log; }, [log]);
  useEffect(() => {
    if (!dirty) return;
    const beforeUnload = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = ""; };
    window.addEventListener("beforeunload", beforeUnload);
    return () => window.removeEventListener("beforeunload", beforeUnload);
  }, [dirty]);
  useImperativeHandle(ref, () => ({ get medicalLogId() { return persisted.current?.medical_log_id; }, remove }));
  async function close() {
    if (!persisted.current) { editor.discard(); onClose(); return; }
    if (await flush()) onClose();
  }
  async function saveCreate() { await flush(true); }
  const disabled = !canEdit || deleting;
  const content = <section className="medical-log-detail" ref={panel} tabIndex={-1} aria-label={log ? "健康日记详情" : navigationLabels.createLog}>
    {log?<WorkspaceToolbar className="reports-detail-toolbar" title={log.title} onBack={() => void close()} />:null}
    <form id={formId} className={`medical-log-form scroll-content content-column${!log?" dialog-body":""}`} onSubmit={event => { event.preventDefault(); void (log ? flush() : saveCreate()); }}>
      <section>
        <div className="group-heading"><h2>基本信息</h2></div>
        <GroupedList layout="fields" density="standard">
          {canEdit ? <>
            <label className="field-row"><span className="field-label">标题</span><input aria-label="日记标题" required disabled={disabled} value={draft.title}
              placeholder="为今天的随记或这次经历起个标题" onChange={event => change({ title: event.target.value })}
              onCompositionStart={() => { composing.current = true; editor.compose(true); }}
              onCompositionEnd={event => { composing.current = false; change({ title: event.currentTarget.value }); editor.compose(false); }}
              onBlur={() => { if (log && !composing.current) void editor.flushOnBlur(); }} /></label>
            <DateField label="日期" value={draft.recorded_on} disabled={disabled} required onChange={value => { if (value) change({ recorded_on: value }, true); }} />
          </> : <>
            <ReadonlyField label="标题" value={draft.title} />
            <ReadonlyField label="日期" value={formatDateOnly(draft.recorded_on)} />
          </>}
        </GroupedList>
      </section>
      <section>
        <div className="group-heading"><h2 id="medical-log-content-heading">日记内容</h2></div>
        {canEdit ? <textarea id="medical-log-content" ref={body} className="medical-log-content" aria-labelledby="medical-log-content-heading" required disabled={disabled}
          rows={3} value={draft.content} placeholder="记录今天的生活、饮食、活动、身体感受或就医经历"
          onChange={event => change({ content: event.target.value })}
          onCompositionStart={() => { composing.current = true; editor.compose(true); }}
          onCompositionEnd={event => { composing.current = false; change({ content: event.currentTarget.value }); editor.compose(false); }}
          onBlur={() => { if (log && !composing.current) void editor.flushOnBlur(); }} /> :
          <div id="medical-log-content" className="medical-log-content">{draft.content}</div>}
      </section>
      {readError ? <p role="alert">{readError}</p> : null}
      {error ? <div className="medical-log-save-error" role="alert"><p>{error}</p>{canEdit && log ?
        <button className="control" type="button" onClick={() => void flush()}><CheckIcon /><span>重试保存</span></button> : null}</div> : null}
      {saving || dirty ? <p className="content-description" role="status">{saving ? "保存中…" : "尚未保存"}</p> : null}
      {log ? canEdit ? <div className="medical-log-actions">
        <button className="control control--danger" type="button" onClick={() => void remove()} disabled={deleting}><TrashIcon /><span>删除日记</span></button>
      </div> : null : null}
    </form>
  </section>;
  return log?content:<ContentDialog creation title={navigationLabels.createLog} onClose={()=>void close()} busy={saving} bareBody actions={<>
    <button className="control control--primary" type="submit" form={formId} disabled={saving||disabled}><CheckIcon/>完成</button>
  </>}>{content}</ContentDialog>;
}
