import { navigationLabels } from "../../components/navigationLabels";
import {useEffect,useRef,useState} from 'react';
import type {MedicationItem} from '../../api/medicationTypes';
import {deleteBatch} from '../../api/medicationApi';
import {PlusIcon,ChevronRightIcon} from '../../components/icons';
import {GroupedList} from '../../components/GroupedList';
import {useListDeleteActions} from '../../components/useListDeleteActions';
import {useActiveScope} from '../../utils/useActiveScope';
import {formatDateOnly} from '../../utils/localTime';
import {MedicationBatchExpiry} from './MedicationBatchExpiry';

export function MedicationExtras({member,item,canEdit,onOpenBatch,onReload,beforeDelete,onSelectionChange}:{member:string;item:MedicationItem;canEdit:boolean;onOpenBatch:(id:string)=>void;onReload:()=>void;beforeDelete:()=>Promise<boolean>;onSelectionChange:(active:boolean)=>void}) {
 const [error,setError]=useState('');const editable=useRef(canEdit);editable.current=canEdit;
 const scope=`${member}:${item.medication_id}`;const isCurrent=useActiveScope(scope);
 const [removed,setRemoved]=useState(new Set<string>());
 const batches=(item.batches??[]).filter(batch=>!removed.has(batch.medication_batch_id));
 const actions=useListDeleteActions({scope,enabled:canEdit,label:'药品批次',countLabel:'个批次',entries:batches.map((batch,index)=>({id:batch.medication_batch_id,name:`批次${index+1}`})),onDelete:async ids=>{
  if(!await beforeDelete())return ids;
  const failed:string[]=[];const deleted:string[]=[];const messages:string[]=[];
  for(const id of ids){
   if(!isCurrent()||!editable.current){failed.push(id);continue;}
   try{await deleteBatch(member,String(item.medication_id),id);deleted.push(id);}
   catch(cause){failed.push(id);messages.push(cause instanceof Error?cause.message:'删除失败');}
  }
  if(isCurrent()){setRemoved(previous=>new Set([...previous,...deleted]));setError(failed.length?`${deleted.length?'部分批次已删除。':''}${failed.length} 个批次未删除：${messages[0]||'没有编辑权限'}`:'');onReload();}
  return failed;
 }});
 useEffect(()=>{onSelectionChange(actions.selectionMode);return()=>onSelectionChange(false);},[actions.selectionMode,onSelectionChange]);
 return <section onKeyDown={actions.onKeyDown}><div className="group-heading"><h2>药品库存</h2></div>{actions.heading}<GroupedList density="standard" selectionMode={actions.selectionMode?'multiple':undefined}>
  {canEdit&&!actions.selectionMode?<button className="control control--row grouped-list-create-button" data-medication-batch="new" type="button" onClick={()=>onOpenBatch('new')}><PlusIcon/>{navigationLabels.addBatch}</button>:null}
  {batches.map((batch,index)=><button key={batch.medication_batch_id} {...actions.rowProps(batch.medication_batch_id)} type="button" className="control control--row medication-batch-summary" data-medication-batch={batch.medication_batch_id} role={actions.selectionMode?'checkbox':undefined} aria-checked={actions.selectionMode?actions.selected(batch.medication_batch_id):undefined} disabled={actions.busy} onClick={()=>actions.selectionMode?actions.toggle(batch.medication_batch_id):onOpenBatch(batch.medication_batch_id)}>{actions.indicator(batch.medication_batch_id)}<span>批次{index+1}</span><span className="content-description medication-batch-details">{batch.expires_on?formatDateOnly(batch.expires_on):'未记录'} · {batch.quantity}<MedicationBatchExpiry expiresOn={batch.expires_on} separated/></span>{!actions.selectionMode?<ChevronRightIcon/>:null}</button>)}
 </GroupedList>{error?<p role="alert">{error}</p>:null}{actions.toolbar}{actions.portal}</section>;
}
