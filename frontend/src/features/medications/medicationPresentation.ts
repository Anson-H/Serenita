import type { MedicationIdentity, MedicationItem, MedicationKind, MedicationPlanValues, MedicationSchedule, MedicationSection } from '../../api/medicationTypes';
import { formatLocalDate, localDateTimeInputValue } from '../../utils/localTime';
export const sectionKinds: Record<MedicationSection,MedicationKind> = {catalog:'medication',plans:'plan'};
export const sectionLabels = {catalog:'药品库存',plans:'用药计划'};
export const kindSections: Record<MedicationKind,MedicationSection> = {medication:'catalog',plan:'plans'};
export const statusLabels: Record<string,string> = {upcoming:'未开始',ongoing:'进行中',ended:'已结束',undated:'时间未确定',taking:'在用',paused:'暂停',stopped:'已停用',completed:'已完成',unknown:'未确认'};
export const scheduleLabels = {as_needed:'按需',daily:'每日',every_n_days:'每隔若干日',weekly:'每周指定日'};
export const itemId = (item: MedicationItem,kind: MedicationKind) => kind === 'plan' ? item.medication_plan_id ?? '' : item.medication_id;
export const medicationName = (identity:Partial<MedicationIdentity>) => [...new Set([identity.brand_name?.trim(),identity.generic_name?.trim()].filter(Boolean))].join(' ');
export const medicationSpecification = (identity:Partial<MedicationIdentity>) => [identity.strength,identity.package_specification].filter(Boolean).join(' · ');
export const itemName = (item: MedicationItem) => medicationName(item.medication_identity??item) || '未命名';
export const browserZone = () => Intl.DateTimeFormat().resolvedOptions().timeZone || 'Asia/Shanghai';
export const emptyPlan = (): MedicationPlanValues => ({starts_at:null,ends_at:null,start_precision:null,end_precision:null,timezone:browserZone(),schedule:null,usage_status:'unknown'});
export function localValue(iso: string,zone: string) {
  const parts=new Intl.DateTimeFormat('en-CA',{timeZone:zone,year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hourCycle:'h23'}).formatToParts(new Date(iso));
  const p=Object.fromEntries(parts.map(part=>[part.type,part.value])); return `${p.year}-${p.month}-${p.day}T${p.hour}:${p.minute}`;
}
export function zonedIso(local: string,zone: string) {
  const target=Date.parse(local.length===10?local+'T00:00:00Z':local+'Z');
  let result=target;
  for(let i=0;i<4;i++) { const actual=Date.parse(localValue(new Date(result).toISOString(),zone)+'Z'); const next=result+target-actual; if(next===result) break; result=next; }
  return new Date(result).toISOString();
}
export const addDay = (value: string,n: number) => { const day=new Date(value+'T00:00:00Z');day.setUTCDate(day.getUTCDate()+n);return day.toISOString().slice(0,10); };

export function medicationLocalClock(plan:MedicationPlanValues,clock:string) {
  if(!clock||plan.timezone===browserZone())return clock;
  const day=localValue(plan.starts_at||new Date().toISOString(),plan.timezone).slice(0,10);
  return localDateTimeInputValue(new Date(zonedIso(`${day}T${clock}`,plan.timezone))).slice(11,16);
}

export function planSummary(item: MedicationItem) {
  const arrangement=item;
  if(!arrangement.starts_at||!arrangement.timezone)return '';
  const period=arrangement.starts_at?`${formatLocalDate(arrangement.starts_at)} 至 ${arrangement.ends_at==='long_term'?'长期':arrangement.ends_at?formatLocalDate(new Date(Date.parse(arrangement.ends_at)-1)):'未知'}`:'用药周期未记录';
  const schedule=arrangement.schedule;
  let frequency=schedule?scheduleLabels[schedule.kind]:'用药频率未记录';
  if(schedule?.kind==='daily'&&schedule.times_per_day)frequency=`每日 ${schedule.times_per_day} 次`;
  if(schedule?.kind==='weekly')frequency=`每周${(schedule.weekdays??[]).map(day=>['一','二','三','四','五','六','日'][day-1]).join('、')}`;
  if(schedule?.kind==='every_n_days')frequency=`每隔 ${schedule.interval_days} 日`;
  const time=schedule?.times?.map(t=>medicationLocalClock(arrangement as MedicationPlanValues,t.time)).join('、');
  return [period,frequency,time||(schedule?.kind==='as_needed'?'无固定时间':'用药时间未记录')].join(' · ');
}

export function frequencyDescription(schedule:MedicationSchedule|null) {
  if(!schedule)return '未记录';
  if(schedule.kind==='weekly')return `每周${[...(schedule.weekdays??[])].sort((a,b)=>a-b).map(day=>['一','二','三','四','五','六','日'][day-1]).join('、')}`;
  if(schedule.kind==='every_n_days')return `每隔 ${schedule.interval_days} 日`;
  return scheduleLabels[schedule.kind];
}
export function timeDescription(plan:MedicationPlanValues) {
  const schedule=plan.schedule;
  if(schedule?.kind==='as_needed')return '按需，无固定时间';
  if(schedule?.times?.length)return schedule.times.map(t=>medicationLocalClock(plan,t.time)).sort().join('、');
  return schedule?.times_per_day?`每日 ${schedule.times_per_day} 次，时间未定`:'未记录';
}
