import {useState} from 'react';
import type {MedicationIdentity} from '../../api/medicationTypes';

function IdentityField({label,value,creating,canEdit,required=false,onChange}:{label:string;value:string;creating:boolean;canEdit:boolean;required?:boolean;onChange:(value:string)=>void}) {
  const [editing,setEditing]=useState(false);
  return <div className="field-row">
    <span className="field-label">{label}</span>
    <span className="field-value">{canEdit&&(creating||editing)?<span className="report-inline-edit">
      <input aria-label={label} autoFocus={!creating} placeholder={required?'必填':'未记录'} required={required} value={value} onChange={event=>onChange(event.target.value)} onBlur={()=>setEditing(false)}/>
    </span>:canEdit?<button type="button" aria-label={`编辑${label}`} className="report-inline-edit-trigger" data-interaction-owner="row" onPointerDown={event=>{event.preventDefault();setEditing(true);}} onClick={()=>setEditing(true)}>{value||'未记录'}</button>:<span>{value||'未记录'}</span>}</span>
  </div>;
}

export function MedicationIdentityFields({identity,creating,canEdit,onChange}:{identity:MedicationIdentity;creating:boolean;canEdit:boolean;onChange:(changes:Partial<MedicationIdentity>)=>void}) {
  const generic=identity.generic_name??'';
  function nameChange(key:'brand_name'|'generic_name',value:string){
    onChange(key === 'generic_name' ? {generic_name:value} : {brand_name:value||null});
  }
  return <>
    <IdentityField label="通用名" value={generic} creating={creating} canEdit={canEdit} required onChange={value=>nameChange('generic_name',value)}/>
    <IdentityField label="商品名" value={identity.brand_name??''} creating={creating} canEdit={canEdit} onChange={value=>nameChange('brand_name',value)}/>
    <IdentityField label="浓度含量" value={identity.strength??''} creating={creating} canEdit={canEdit} onChange={value=>onChange({strength:value||null})}/>
    <IdentityField label="包装规格" value={identity.package_specification??''} creating={creating} canEdit={canEdit} onChange={value=>onChange({package_specification:value||null})}/>
  </>;
}
