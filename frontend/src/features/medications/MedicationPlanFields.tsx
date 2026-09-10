import { navigationLabels } from "../../components/navigationLabels";
import { type ReactNode } from 'react';
import type { MedicationPlanValues } from '../../api/medicationTypes';
import { Field,Group } from './MedicationFields';
import { browserZone,addDay,localValue,medicationLocalClock,frequencyDescription,timeDescription } from './medicationPresentation';
import { localDateTimeInputValue,localIsoString } from '../../utils/localTime';
import { DateField } from '../../components/DateField';
import { ChevronRightIcon } from '../../components/icons';
import type { MedicationScheduleSetting } from './MedicationSchedulePage';

function localDay(value:string|null,end=false) {
  if(!value || value === 'long_term')return value;
  const date=new Date(value);if(end)date.setTime(date.getTime()-1);
  return localDateTimeInputValue(date).slice(0,10);
}
function localBoundary(day:string,end=false) {return localIsoString(new Date(`${end?addDay(day,1):day}T00:00:00`));}
export function MedicationPlanFields({plan:p,onChange:edit,onOpenSetting,disabled,children}:{plan:MedicationPlanValues;onChange:(changes:Partial<MedicationPlanValues>)=>void;onOpenSetting:(setting:MedicationScheduleSetting)=>void;disabled:boolean;children?:ReactNode}) {
  function period(start:string|null,end:string|null) {
    let next=p.schedule;
    if(next){
      next={...next,times:next.times?.map(t=>({...t,time:medicationLocalClock(p,t.time)}))};
      if(next.kind==='every_n_days'&&(!next.anchor_date||next.anchor_date===(p.starts_at?localValue(p.starts_at,p.timezone).slice(0,10):null)))next.anchor_date=start;
    }
    const datedEnd = end && end !== 'long_term' ? end : null;
    edit({starts_at:start?localBoundary(start):null,start_precision:start?'date':null,ends_at:end==='long_term'?'long_term':datedEnd?localBoundary(datedEnd,true):null,end_precision:datedEnd?'date':null,timezone:browserZone(),schedule:next});
  }
  const start=localDay(p.starts_at);const end=localDay(p.ends_at,true);
  return <section className="medication-plan-fields">
    <Group title="用药安排">
        {(['frequency','times'] as const).map(setting=><button key={setting} className="field-row medication-setting-row" type="button" aria-label={setting==='frequency'?navigationLabels.frequency:navigationLabels.times} data-interaction-owner="row" onClick={()=>onOpenSetting(setting)}>
          <span className="field-label">{setting==='frequency'?navigationLabels.frequency:navigationLabels.times}</span><span className="field-value medication-setting-value"><span className="content-description">{setting==='frequency'?frequencyDescription(p.schedule):timeDescription(p)}</span><ChevronRightIcon/></span>
        </button>)}
        <Field label="每次剂量" value={p.dose_text} disabled={disabled} onChange={v=>edit({dose_text:v||null})}/>
        <div className="field-row"><span className="field-label">用药周期</span><div className="field-value medication-period-values"><DateField compact label="开始日期" required value={start} emptyLabel="必填" disabled={disabled} onChange={v=>period(v,end)}/><span aria-hidden="true">至</span><DateField compact label="结束日期" value={end} allowLongTerm disabled={disabled} onChange={v=>period(start,v)}/></div></div>
        <Field label="给药途径" value={p.route} disabled={disabled} onChange={v=>edit({route:v||null})}/>
        {children}
    </Group>
  </section>;
}
