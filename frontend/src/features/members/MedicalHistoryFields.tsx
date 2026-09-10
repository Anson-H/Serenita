import { useLayoutEffect, useRef } from "react";
import { MEDICAL_HISTORY_FIELDS } from "../../api/medicalHistoryApi";
import { GroupedList } from "../../components/GroupedList";
import type { useMedicalHistory } from "./useMedicalHistory";

export function MedicalHistoryFields({ history, canEdit, disabled }: {
  history: ReturnType<typeof useMedicalHistory>; canEdit: boolean; disabled: boolean;
}) {
  const group = useRef<HTMLDivElement>(null);
  useLayoutEffect(() => {
    const areas = Array.from(group.current?.querySelectorAll("textarea") ?? []);
    const resize = (area: HTMLTextAreaElement) => {
      area.style.height = "auto";
      area.style.height = `${area.scrollHeight}px`;
    };
    areas.forEach(resize);
    const widths = new Map<Element, number>();
    const observer = new ResizeObserver(entries => {
      entries.forEach(entry => {
        const width = entry.contentRect.width;
        if (widths.get(entry.target) === width) return;
        widths.set(entry.target, width);
        resize(entry.target as HTMLTextAreaElement);
      });
    });
    areas.forEach(area => observer.observe(area));
    return () => observer.disconnect();
  }, [history.data, history.draft, canEdit]);
  return <section className="member-history" aria-label="既往史">
    <div className="group-heading"><h3>既往史</h3></div>
    {!history.data ? <p className="content-description">{history.error || "正在读取既往史…"}</p> :
      <GroupedList ref={group} layout="fields" density="standard">
        {MEDICAL_HISTORY_FIELDS.map(([field, label, description]) => {
          const value = (canEdit ? history.draft[field] : undefined) ?? history.data?.history[field].text ?? "";
          return canEdit ? <label className="field-row member-history-row" key={field}>
            <span className="field-label" title={description}>{label}</span>
            <textarea className="field-value" aria-label={label} title={description} placeholder={description} rows={1}
              value={value} disabled={disabled} onChange={event => history.change(field, event.target.value)}
              onCompositionStart={history.startComposition} onCompositionEnd={event => history.endComposition(field, event.currentTarget.value)} />
          </label> : <div className="field-row member-history-row" key={field}>
            <span className="field-label">{label}</span>
            <span className="field-value">{value || "未记录"}</span>
          </div>;
        })}
      </GroupedList>}
    {history.data && history.error ? <p role="alert">{history.error}</p> : null}
    {history.saving ? <p role="status" className="content-description">正在保存既往史…</p> : null}
  </section>;
}
