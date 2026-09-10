import { navigationLabels } from "../../components/navigationLabels";
import {useEffect,useRef,useState} from 'react';
import type {MedicationPlanValues,MedicationSchedule} from '../../api/medicationTypes';
import {GroupedList,GroupedCheckboxRow} from '../../components/GroupedList';
import {DateField} from '../../components/DateField';
import {localDateTimeInputValue,localIsoString} from '../../utils/localTime';
import {focusWithoutScroll,isImeComposing} from '../../utils/inputMethod';
import {MedicationTimeFields} from './MedicationTimeFields';
import {Field,Group} from './MedicationFields';
import {browserZone,localValue,medicationLocalClock,scheduleLabels} from './medicationPresentation';

export type MedicationScheduleSetting='frequency'|'times';
function validationError(draft:MedicationSchedule|null) {
  if(draft?.kind==='weekly'&&!draft.weekdays?.length)return '请选择至少一个用药星期。';
  if(draft?.kind==='every_n_days'&&(!Number.isInteger(draft.interval_days)||(draft.interval_days??0)<1))return '请填写大于 0 的整数间隔天数。';
  if(draft?.kind==='every_n_days'&&!draft.anchor_date)return '请选择起算日期。';
  const times=draft?.times??[];
  if(times.some(t=>!/^([01]\d|2[0-3]):[0-5]\d$/.test(t.time)))return '请填写完整的用药时间。';
  if(new Set(times.map(t=>t.time)).size!==times.length)return '用药时间不能重复，请调整或删除重复时间。';
  if(draft?.times_per_day!=null&&(!Number.isInteger(draft.times_per_day)||draft.times_per_day<1||draft.times_per_day>96))return '每日次数须为 1 至 96 的整数。';
  return '';
}
export function MedicationSchedulePage({plan,setting,disabled,onBack,onChange,onSave,saveError,initialDraft,onDraftChange}:{plan:MedicationPlanValues;setting:MedicationScheduleSetting;disabled:boolean;onBack:()=>void;onChange:(schedule:MedicationSchedule|null)=>void;onSave:()=>Promise<boolean>;saveError:string;initialDraft?:MedicationSchedule|null;onDraftChange:(draft:MedicationSchedule|null|undefined)=>void}) {
  const [draft,setDraft]=useState<MedicationSchedule|null>(()=>initialDraft!==undefined?initialDraft:plan.schedule?{...plan.schedule,times:plan.schedule.times?.map(t=>({time:medicationLocalClock(plan,t.time)}))}:null);
  const [error,setError]=useState(()=>initialDraft===undefined?'':validationError(initialDraft));
  async function back(){if(disabled||await onSave())onBack();}
  const heading=useRef<HTMLElement>(null);
  useEffect(()=>focusWithoutScroll(heading.current),[]);
  const kind=draft?.kind;
  const fixed=kind==='daily'||kind==='weekly'||kind==='every_n_days';
  const title=setting==='frequency'?navigationLabels.frequency:navigationLabels.times;
  function apply(next:MedicationSchedule|null){
    if(disabled)return;
    const message=validationError(next);
    setDraft(next);setError(message);onDraftChange(message?next:undefined);
    if(message)return;
    const day=plan.starts_at?localDateTimeInputValue(new Date(plan.starts_at)).slice(0,10):localDateTimeInputValue(new Date()).slice(0,10);
    onChange(next?{...next,times:(next.times??[]).map(t=>({time:plan.timezone===browserZone()?t.time:localValue(localIsoString(new Date(`${day}T${t.time}`)),plan.timezone).slice(11,16)})).sort((a,b)=>a.time.localeCompare(b.time))}:null);
  }
  function update(changes:Partial<MedicationSchedule>){if(draft)apply({...draft,...changes});}
  function select(value:string){
    if(value===(kind??''))return;
    if(!value){apply(null);return;}
    apply({kind:value as MedicationSchedule['kind'],times:value==='as_needed'?[]:draft?.times??[],
      ...(value==='every_n_days'?{interval_days:null,anchor_date:plan.starts_at?localValue(plan.starts_at,plan.timezone).slice(0,10):null}:{}),
      ...(value==='weekly'?{weekdays:[]}:{}),
    });
  }
  return <section className="medication-schedule-page" ref={heading} tabIndex={-1} aria-label={`${title}设置`} onKeyDown={event=>{if((event.target as HTMLElement).closest('[data-modal-focus-scope], [aria-modal="true"]'))return;if(event.key==='Escape'&&!event.defaultPrevented&&!isImeComposing(event.nativeEvent)){event.preventDefault();event.stopPropagation();void back();}}}>
    <div className="medication-schedule-body content-column">
      {setting==='frequency'?<>
        <GroupedList density="standard" role="group" aria-label="选择用药频率">
          {Object.entries({'':'未记录',...scheduleLabels}).map(([value,label])=><button className="control control--row medication-frequency-choice" key={value} type="button" aria-pressed={(kind??'')===value} disabled={disabled} onClick={()=>select(value)}><span>{label}</span></button>)}
        </GroupedList>
        {kind==='weekly'?<section><div className="group-heading"><h2>用药星期</h2></div><GroupedList density="standard" selectionMode="multiple" role="group" aria-label="用药星期">
          {['一','二','三','四','五','六','日'].map((day,i)=><GroupedCheckboxRow key={day} label={`星期${day}`} disabled={disabled} checked={draft?.weekdays?.includes(i+1)??false} onChange={checked=>update({weekdays:checked?[...(draft?.weekdays??[]),i+1].sort((a,b)=>a-b):(draft?.weekdays??[]).filter(d=>d!==i+1)})}/>)}
        </GroupedList></section>:null}
        {kind==='every_n_days'?<Group title="间隔设置"><Field label="间隔天数" type="number" disabled={disabled} value={draft?.interval_days} onChange={value=>update({interval_days:value?Number(value):null})}/><div className="field-row"><span className="field-label">起算日期</span><div className="field-value"><DateField compact label="起算日期" required value={draft?.anchor_date??null} disabled={disabled} onChange={value=>update({anchor_date:value})}/></div></div></Group>:null}
      </>:fixed?<>
        <MedicationTimeFields times={draft?.times??[]} disabled={disabled} onChange={times=>update({times,times_per_day:null})}/>
        {kind==='daily'&&!draft?.times?.length?<Group title="时间未定"><Field label="每日次数" type="number" disabled={disabled} value={draft?.times_per_day} onChange={value=>update({times_per_day:value?Number(value):null})}/></Group>:null}
      </>:<GroupedList density="standard"><div className="field-row"><span className="field-label">{navigationLabels.times}</span><span className="field-value">{kind==='as_needed'?'按需':'未记录'}</span></div></GroupedList>}
      {error||saveError?<div role="alert"><p>{error||saveError}</p>{saveError&&!disabled?<button className="control" type="button" onClick={async()=>{if(await onSave())focusWithoutScroll(heading.current);}}>重试保存</button>:null}</div>:null}
    </div>
  </section>;
}
