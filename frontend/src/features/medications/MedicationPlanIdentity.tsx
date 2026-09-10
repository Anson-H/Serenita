import { navigationLabels } from "../../components/navigationLabels";
import { NavigationTitle } from "../../components/NavigationTitle";
import { EmptyState } from "../../components/EmptyState";
import {useEffect,useRef,useState,useId} from 'react';
import {createPortal} from 'react-dom';
import type {MedicationIdentity,MedicationItem} from '../../api/medicationTypes';
import {listMedications,readMedication} from '../../api/medicationApi';
import {GroupedList} from '../../components/GroupedList';
import {IdentityRowCopy} from '../../components/IdentityRowCopy';
import {useModalDialog} from '../../components/useModalDialog';
import {MedicationIcon,SwapHorizontalIcon,XIcon} from '../../components/icons';
import {medicationName,medicationSpecification} from './medicationPresentation';

export function MedicationPlanIdentity({member,identity,medicationId,canEdit,onChange}:{member:string;identity:MedicationIdentity;medicationId:string|null;canEdit:boolean;onChange:(id:string|null,identity:MedicationIdentity)=>void}){
  const [open,setOpen]=useState(false);
  useEffect(()=>setOpen(false),[member,canEdit]);
  const name=medicationName(identity)||'请选择药品';const specification=medicationSpecification(identity);
  return <>
    <section className="identity-row medication-plan-identity" aria-label="计划药品">
      <span className="health-member-avatar" aria-hidden="true"><MedicationIcon className="health-member-avatar-icon"/></span>
      <IdentityRowCopy title={name} description={specification||undefined}/>
      {canEdit?<button type="button" className="control control--titlebar control--icon control--ghost" data-interaction-owner="self" aria-label={navigationLabels.switchMedication} title={navigationLabels.switchMedication} aria-haspopup="dialog" onClick={()=>setOpen(true)}><SwapHorizontalIcon/></button>:null}
    </section>
    {open&&canEdit?<MedicationPicker key={member} member={member} medicationId={medicationId} onClose={()=>setOpen(false)} onSelect={(id,value)=>{onChange(id,value);setOpen(false);}}/>:null}
  </>;
}

export function MedicationPicker({member,medicationId,onClose,onSelect}:{member:string;medicationId:string|null;onClose:()=>void;onSelect:(id:string|null,value:MedicationIdentity)=>void}){
  const [items,setItems]=useState<MedicationItem[]>([]);const [query,setQuery]=useState('');const [cursor,setCursor]=useState<string|null>(null);
  const [loading,setLoading]=useState(true);const [busy,setBusy]=useState(false);const [error,setError]=useState('');const [reload,setReload]=useState(0);
  const dialog=useRef<HTMLFormElement>(null);const active=useRef(true);const revision=useRef(0);const selection=useRef<AbortController|null>(null);const titleId=useId();
  const title=navigationLabels.switchMedication;
  useModalDialog({active:true,dialogRef:dialog,onEscape:onClose,escapeDisabled:busy});
  useEffect(()=>{active.current=true;return()=>{active.current=false;selection.current?.abort();};},[]);
  const filters={query,status:'',after_date:'',before_date:'',undated:false};
  useEffect(()=>{
    const controller=new AbortController();const token=++revision.current;setLoading(true);setError('');setItems([]);setCursor(null);
    void listMedications(member,'medication',filters,undefined,controller.signal).then(result=>{
      if(!controller.signal.aborted&&token===revision.current){setItems(result.items);setCursor(result.next_cursor);}
    }).catch(cause=>{if(!controller.signal.aborted&&token===revision.current)setError(cause.message);}).finally(()=>{if(!controller.signal.aborted&&token===revision.current)setLoading(false);});
    return()=>controller.abort();
  },[member,query,reload]);
  async function more(){
    if(!cursor||loading||busy)return;const token=revision.current;setLoading(true);
    try{const result=await listMedications(member,'medication',filters,cursor);if(active.current&&token===revision.current){setItems(current=>[...current,...result.items]);setCursor(result.next_cursor);}}
    catch(cause){if(active.current&&token===revision.current)setError(cause instanceof Error?cause.message:'药品读取失败');}
    finally{if(active.current&&token===revision.current)setLoading(false);}
  }
  async function select(id:string){
    if(busy)return;setBusy(true);setError('');const controller=new AbortController();selection.current=controller;
    try{
      const item=await readMedication(member,'medication',id,controller.signal);
      const value=Object.fromEntries(['generic_name','brand_name','strength','package_specification'].map(key=>[key,item[key as keyof MedicationIdentity]??null])) as MedicationIdentity;
      if(active.current&&!controller.signal.aborted)onSelect(id,value);
    }catch(cause){if(active.current&&!controller.signal.aborted)setError(cause instanceof Error?cause.message:'切换药品失败');}
    finally{if(active.current)setBusy(false);}
  }
  return createPortal(<div className="content-dialog-backdrop dialog-viewport-backdrop" onMouseDown={event=>{if(event.target===event.currentTarget&&!busy)onClose();}}>
    <form role="dialog" aria-modal="true" aria-labelledby={titleId} ref={dialog} className="content-dialog dialog-viewport-surface dialog-title-ellipsis" onSubmit={event=>{event.preventDefault();event.stopPropagation();}}>
      <header className="dialog-titlebar"><NavigationTitle id={titleId} data-modal-initial-focus tabIndex={-1} title={title} /><button type="button" className="control control--titlebar control--icon control--ghost titlebar-icon-control" aria-label={'关闭'+title} disabled={busy} onClick={onClose}><XIcon/></button></header>
      <div className="dialog-body medication-picker-body scroll-content">
          <input type="search" aria-label="搜索目录药品" placeholder="搜索药名或规格" disabled={busy} value={query} onChange={event=>setQuery(event.target.value)}/>
          <GroupedList density="standard" selectionMode="single" aria-label="可切换的药品">{items.map(item=><button type="button" className="control control--row medication-picker-choice" data-interaction-owner="row" key={item.medication_id} aria-current={item.medication_id===medicationId?'true':undefined} disabled={busy} onClick={()=>void select(String(item.medication_id))}>
            <MedicationIcon/><span><strong>{medicationName(item)}</strong><span className="content-description">{medicationSpecification(item)}</span></span>
          </button>)}</GroupedList>
          {loading?<p role="status">正在读取药品…</p>:!items.length&&!error?<EmptyState layout="inline" title={query?'没有匹配的药品':'目录暂无药品，请先在设置的药品目录中添加'} />:null}
          {cursor?<button type="button" className="control" disabled={busy||loading} onClick={()=>void more()}>更多药品</button>:null}
        {error?<div role="alert"><p>{error}</p><button type="button" className="control" disabled={busy} onClick={()=>setReload(value=>value+1)}>重新读取</button></div>:null}
      </div>
    </form>
  </div>,document.body);
}
