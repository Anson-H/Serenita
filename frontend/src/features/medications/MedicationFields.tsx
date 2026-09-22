import { type ReactNode } from 'react';
import { GroupedList } from '../../components/GroupedList';
import { SelectPopover } from '../../components/SelectPopover';

export function Field({label,value,onChange,disabled=false,required=false,type='text'}:{label:string;value:unknown;onChange:(value:string)=>void;disabled?:boolean;required?:boolean;type?:string}) {
  return <label className="field-row"><span className="field-label">{label}</span>{disabled?<span className="field-value">{String(value??'')||'未记录'}</span>:<input aria-label={label} value={String(value??'')} required={required} type={type} placeholder={required?'必填':'未记录'} onChange={e=>onChange(e.target.value)}/>}</label>;
}
export function NotesField({value,onChange,disabled}:{value:unknown;onChange:(value:string)=>void;disabled:boolean}) {
  const text=String(value??'');
  return <label className="field-row"><span className="field-label">备注</span><span className="field-value">{disabled?<span>{text||'未记录'}</span>:<span className="report-inline-edit report-content-sized-editor">
    <span aria-hidden="true" className="report-inline-edit-trigger report-inline-edit-size-mirror"><span>{text?`${text}\u200b`:'未记录'}</span></span>
    <textarea aria-label="备注" rows={1} placeholder="未记录" value={text} onChange={event=>onChange(event.target.value)}/>
  </span>}</span></label>;
}
export function Choice<Value extends string>({label,value,choices,onChange,disabled=false}:{label:string;value:Value;choices:Record<Value,string>;onChange:(value:Value)=>void;disabled?:boolean}) {
  const options: { value: Value; label: string }[] = [];
  for (const value in choices) options.push({ value, label: choices[value] });
  return <div className="field-row"><span className="field-label">{label}</span>{disabled?<span className="field-value">{choices[value]||value||'未记录'}</span>:<SelectPopover menuWidth="content" menuAlign="end" ariaLabel={label} value={value} options={options} interactionOwner="row" onChange={onChange}/>}</div>;
}
export function Group({title,children}:{title:string;children:ReactNode}) { return <section><div className="group-heading"><h2>{title}</h2></div><GroupedList layout="fields" density="standard">{children}</GroupedList></section>; }
