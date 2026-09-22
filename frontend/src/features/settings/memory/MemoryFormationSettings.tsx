import { useEffect, useMemo, useRef, useState } from 'react';
import { ApiRequestError } from "../../../api/transport/request";
import { Switch } from "../../../components/Switch";
import { GroupedList, GroupedCheckboxRow } from "../../../components/GroupedList";
import { useAutosaveResource } from "../../../utils/useAutosaveResource";
import { saveBeforeNavigation } from "../../../utils/pendingNavigation";
import { randomUuid } from "../../../utils/randomUuid";
import { getMemorySettings, saveMemorySettings, memoryCategories, type MemoryCategory, type MemorySettings } from "../../../api/memory/memoryApi";

type Draft = Pick<MemorySettings, 'formation_state' | 'source_categories'>;
type Command = Parameters<typeof saveMemorySettings>[1];
function FormationEditor({ memberId, value, onSaved }: { memberId: string; value: MemorySettings; onSaved: (value: MemorySettings) => void }) {
  const head = useRef(value.setting?.setting_id ?? null), pending = useRef<Command | null>(null);
  useEffect(() => { head.current = value.setting?.setting_id ?? null; }, [value.setting?.setting_id]);
  const server = useMemo(() => ({ formation_state: value.formation_state, source_categories: value.source_categories }), [value]);
  async function submit(command: Command) {
    try { return await saveMemorySettings(memberId, command); }
    catch (cause) {
      if (cause instanceof ApiRequestError && cause.status >= 400 && cause.status < 500 && ![408, 429].includes(cause.status)) {
        pending.current = null;
        if (cause.status === 409) { const current = await getMemorySettings(memberId); head.current = current.setting?.setting_id ?? null; onSaved(current); }
      }
      throw cause;
    }
  }
  const editor = useAutosaveResource<Draft>({
    resourceKey: `memory-settings:${memberId}`, server, enabled: value.can_manage,
    validate: draft => draft.formation_state === 'enabled' && !draft.source_categories.length ? '请至少选择一类资料。' : '',
    save: async draft => {
      if (pending.current) {
        const previous = pending.current, confirmed = await submit(previous); head.current = confirmed.setting?.setting_id ?? null; pending.current = null; onSaved(confirmed);
        if (previous.formation_state === draft.formation_state && JSON.stringify(previous.source_categories) === JSON.stringify(draft.source_categories)) return { formation_state: confirmed.formation_state, source_categories: confirmed.source_categories };
      }
      const command = { ...draft, previous_setting_id: head.current, operation_id: randomUuid() }; pending.current = command;
      const confirmed = await submit(command); head.current = confirmed.setting?.setting_id ?? null; pending.current = null; onSaved(confirmed);
      return { formation_state: confirmed.formation_state, source_categories: confirmed.source_categories };
    }
  });
  function change(patch: Partial<Draft>) { editor.change(patch); void editor.flush(Boolean(pending.current && !editor.controller.snapshot().pending)); }
  return <>
    <GroupedList density="standard" layout="fields"><label className="field-row"><span>自动形成记忆</span><Switch label="自动形成记忆" checked={editor.draft.formation_state === 'enabled'} onChange={checked => change({ formation_state: checked ? 'enabled' : 'paused' })} /></label></GroupedList>
    <fieldset><legend>允许自动处理的资料范围</legend><GroupedList density="standard">{Object.entries(memoryCategories).map(([key, label]) => <GroupedCheckboxRow key={key} label={label} checked={editor.draft.source_categories.includes(key as MemoryCategory)} onChange={checked => {
      const current = editor.controller.snapshot().draft.source_categories;
      change({ source_categories: checked ? [...current, key as MemoryCategory] : current.filter(item => item !== key) });
    }} />)}</GroupedList></fieldset>
    {editor.error ? <p role="alert">{editor.error}<button className="control control--secondary" type="button" onClick={() => void editor.flush()}>重试保存</button></p> : null}
  </>;
}

export function MemoryFormationSettings({ memberId, accessRevision }: { memberId: string; accessRevision: number }) {
  const [value, setValue] = useState<MemorySettings | null>(null), [error, setError] = useState(''), [refresh, setRefresh] = useState(0);
  const generation = useRef(0);
  useEffect(() => {
    const controller = new AbortController(), version = ++generation.current; setValue(null); setError('');
    void getMemorySettings(memberId, controller.signal).then(next => { if (!controller.signal.aborted && version === generation.current) setValue(next); })
      .catch(cause => { if (!controller.signal.aborted && version === generation.current) setError(cause instanceof Error ? cause.message : '记忆设置无法读取。'); });
    return () => { controller.abort(); generation.current += 1; };
  }, [memberId, accessRevision, refresh]);
  useEffect(() => {
    const reset = () => { generation.current += 1; setValue(null); setRefresh(v => v + 1); }; const focus = () => { void saveBeforeNavigation().then(saved => { if (saved) reset(); }); };
    window.addEventListener('focus', focus); window.addEventListener('serenita:member-access-changed', reset);
    return () => { window.removeEventListener('focus', focus); window.removeEventListener('serenita:member-access-changed', reset); };
  }, []);
  const version = generation.current;
  return <section className="memory-formation-settings" aria-label="记忆控制">
    {!value && !error ? <p role="status">正在读取设置…</p> : null}
    {value?.can_manage ? <FormationEditor memberId={memberId} value={value} onSaved={next => { if (version === generation.current) setValue(next); }} /> : value ? <p>记忆形成设置由健康档案所有者管理。</p> : null}
    {error ? <p role="alert">{error}<button className="control control--secondary" type="button" onClick={() => setRefresh(v => v + 1)}>重新读取</button></p> : null}
  </section>;
}
