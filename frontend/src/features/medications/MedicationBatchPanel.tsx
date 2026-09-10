import type { Ref } from "react";
import type {MedicationBatch,MedicationItem} from '../../api/medicationTypes';
import {Field,NotesField} from './MedicationFields';
import {GroupedList} from '../../components/GroupedList';
import {DateField} from '../../components/DateField';
import {WorkspaceToolbar} from '../../components/WorkspaceToolbar';
import {TrashIcon} from '../../components/icons';
import {formatDateOnly} from '../../utils/localTime';
import {useBatchEditor} from './useBatchEditor';
import {MedicationBatchExpiry} from './MedicationBatchExpiry';

export function MedicationBatchPanel({scrollRef,member,item,batchId,canEdit,onClose,onSaved,onDeleted}:{scrollRef?:Ref<HTMLDivElement>;member:string;item:MedicationItem;batchId:string;canEdit:boolean;onClose:()=>void;onSaved:(batch:MedicationBatch)=>void;onDeleted:()=>void}) {
 const original=item.batches?.find(batch=>batch.medication_batch_id===batchId);
 const editor=useBatchEditor(member,String(item.medication_id),original,canEdit,onSaved,onDeleted);
 const {draft,change}=editor;const missing=!original;const disabled=!canEdit||editor.deleting;
 const batchIndex=(item.batches??[]).findIndex(batch=>batch.medication_batch_id===(editor.savedId??batchId));
 const title=batchIndex>=0?`批次${batchIndex+1}`:'药品批次';
 return <>
  <WorkspaceToolbar title={title} onBack={editor.deleting?undefined:async()=>{if(await editor.flush())onClose();}}/>
  <div ref={scrollRef} className="report-detail-scroll scroll-content content-column">
   {missing?<p role="alert">该批次已删除或不可访问。</p>:<form className="medication-editor" onSubmit={event=>{event.preventDefault();void editor.flush();}} onBlur={()=>void editor.flushOnBlur()} onCompositionStart={()=>editor.compose(true)} onCompositionEnd={()=>editor.compose(false)}>
    <GroupedList layout="fields" density="standard">
     {canEdit?<DateField label="有效期" emptyLabel="未知" value={draft.expires_on} disabled={disabled} onChange={expires_on=>change({expires_on})}/>:<Field label="有效期" value={draft.expires_on?formatDateOnly(draft.expires_on):null} disabled onChange={()=>{}}/>}
     <label className="field-row"><span className="field-label">数量</span><span className="field-value medication-batch-quantity">{disabled?<span>{draft.quantity||'未记录'}</span>:<input className="field-inline-input" aria-label="数量" value={draft.quantity} required placeholder="必填" onChange={event=>change({quantity:event.target.value})}/>}<MedicationBatchExpiry expiresOn={draft.expires_on} separated/></span></label>
     <NotesField value={draft.notes} disabled={disabled} onChange={notes=>change({notes:notes||null})}/>
    </GroupedList>
    {editor.error?<p role="alert">{editor.error}</p>:null}
    {editor.saving||editor.dirty?<p className="content-description" role="status">{editor.saving?'正在保存…':'未保存'}</p>:null}
    {canEdit&&editor.savedId?<button className="control control--danger removal-action-control" type="button" disabled={editor.deleting} onClick={()=>void editor.remove()}><TrashIcon/>删除批次</button>:null}
   </form>}
  </div>
 </>;
}
