import {MedicationPicker} from './MedicationPlanIdentity';
import {medicationName} from './medicationPresentation';
import type {MedicationIdentity} from '../../api/medicationTypes';
import { navigationLabels } from "../../components/navigationLabels";
import {useId,useRef,useState} from 'react';
import type {MedicationBatch} from '../../api/medicationTypes';
import {saveBatch} from '../../api/medicationApi';
import {ContentDialog} from '../../components/ContentDialog';
import {GroupedList} from '../../components/GroupedList';
import {DateField} from '../../components/DateField';
import {CheckIcon} from '../../components/icons';
import {NotesField} from './MedicationFields';

export function MedicationBatchCreateDialog({member,medication,onClose,onSaved}:{member:string;medication?:string;onClose:()=>void;onSaved:(batch:MedicationBatch)=>void}) {
  const [selectedMedication,setSelectedMedication]=useState(medication??'');
  const [identity,setIdentity]=useState<MedicationIdentity>({generic_name:''});
  const [picking,setPicking]=useState(false);
  const [quantity,setQuantity]=useState(''),[expiresOn,setExpiresOn]=useState<string|null>(null),[notes,setNotes]=useState<string|null>(null);
  const [busy,setBusy]=useState(false),[error,setError]=useState('');
  const request=useRef({id:crypto.randomUUID(),payload:null as {quantity:string;expires_on:string|null;notes:string|null}|null,savedId:undefined as string|undefined}),running=useRef(false),formId=useId();
  async function submit(){
    if(running.current)return;
    if(!selectedMedication){setError('请选择设置目录中的药品。');return;}
    if(!/^\d+(?:\.\d+)?$/.test(quantity)){setError('请填写有效的非负数量。');return;}
    const values={quantity,expires_on:expiresOn,notes};
    request.current.payload??=values;
    running.current=true;setBusy(true);setError('');
    try{
      const creating=!request.current.savedId;
      let saved=await saveBatch(member,selectedMedication,request.current.savedId?values:request.current.payload,request.current.savedId,request.current.id);
      request.current.savedId=saved.medication_batch_id;
      if(creating&&JSON.stringify(request.current.payload)!==JSON.stringify(values))saved=await saveBatch(member,selectedMedication,values,saved.medication_batch_id);
      onSaved(saved);
    }
    catch(cause){setError(cause instanceof Error?cause.message:'批次未保存');}
    finally{running.current=false;setBusy(false);}
  }
  return <ContentDialog creation title={medication?navigationLabels.addBatch:'添加药品批次'} busy={busy} onClose={onClose} actions={<><button className="control control--primary" type="submit" form={formId} disabled={busy||picking}><CheckIcon/>{busy?'保存中…':'完成'}</button></>}>
    {!medication?<button type="button" className="control control--row" onClick={()=>setPicking(true)} disabled={busy||request.current.payload!==null}>选择药品：{medicationName(identity)||'未选择'}</button>:null}
    {picking?<MedicationPicker member={member} medicationId={selectedMedication||null} onClose={()=>setPicking(false)} onSelect={(id,value)=>{setSelectedMedication(id||'');setIdentity(value);setPicking(false);}}/>:null}
    <form id={formId} onSubmit={event=>{event.preventDefault();void submit();}}><GroupedList layout="fields" density="standard">
      <DateField label="有效期" emptyLabel="未知" value={expiresOn} disabled={busy||picking} onChange={setExpiresOn}/>
      <label className="field-row"><span className="field-label">数量</span><input aria-label="数量" required maxLength={120} inputMode="decimal" disabled={busy||picking} value={quantity} onChange={event=>setQuantity(event.target.value)}/></label>
      <NotesField value={notes} disabled={busy||picking} onChange={setNotes}/>
    </GroupedList>{error?<p role="alert">{error}</p>:null}</form>
  </ContentDialog>;
}
