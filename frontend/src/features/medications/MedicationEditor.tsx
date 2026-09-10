import { navigationLabels } from "../../components/navigationLabels";
import type {MedicationNavigation} from "./MedicationCreateDialog";
import {useEffect,useImperativeHandle,useLayoutEffect,useRef,useState,type Ref} from 'react';
import type {MedicationKind,MedicationItem,MedicationPrescriptionType,MedicationSchedule} from '../../api/medicationTypes';
import {medicationSourceUrl} from '../../api/medicationApi';
import {Choice,Group,NotesField} from './MedicationFields';
import {MedicationIdentityFields} from './MedicationIdentityFields';
import {MedicationSources} from './MedicationSources';
import {MedicationPlanFields} from './MedicationPlanFields';
import {MedicationSchedulePage,type MedicationScheduleSetting} from './MedicationSchedulePage';
import {type ScrollPositionSnapshot,focusWithoutScroll} from '../../utils/inputMethod';
import {MedicationExtras} from './MedicationExtras';
import {useMedicationEditor} from './useMedicationEditor';
import {MedicationPlanIdentity} from './MedicationPlanIdentity';
import {TrashIcon} from '../../components/icons';
import { useScrollRegion } from "../../components/ScrollRegion";
import { itemId } from './medicationPresentation';

export type MedicationEditorHandle = { id: string | undefined; remove: () => Promise<boolean> };

export function MedicationEditor({member,kind,item,canEdit,onSaved,onDeleted,onReload,onSavingChange,onOpenBatch,onSchedulePageChange,formId,onNavigationChange,ref,catalogMode=false}:{catalogMode?:boolean;ref?:Ref<MedicationEditorHandle>;member:string;kind:MedicationKind;item:MedicationItem|null;canEdit:boolean;onSaved:(i:MedicationItem)=>void;onDeleted:()=>void;onReload:()=>void;onSavingChange?:(saving:boolean)=>void;onOpenBatch?:(id:string)=>void;onSchedulePageChange?:(open:boolean)=>void;formId?:string;onNavigationChange?:(navigation:MedicationNavigation|null)=>void}) {
  const informationEditable=canEdit&&catalogMode;
  const editor=useMedicationEditor(member,kind,item,canEdit,onSaved,onDeleted,catalogMode);
  useImperativeHandle(ref,()=>({id:item?itemId(item,kind):undefined,remove:editor.remove}));
  useEffect(()=>onSavingChange?.(editor.saving),[editor.saving,onSavingChange]);
  const [schedulePage,setSchedulePage]=useState<{setting:MedicationScheduleSetting}|null>(null);
  const [batchSelectionMode,setBatchSelectionMode]=useState(false);
  const surface=useRef<HTMLElement|null>(null);
  const scrollRegion=useScrollRegion();
  const scheduleDrafts=useRef(new Map<string,MedicationSchedule|null>());
  const returnScroll=useRef<ScrollPositionSnapshot|null>(null);
  const scheduleOpen=!!schedulePage;
  useLayoutEffect(()=>{onSchedulePageChange?.(scheduleOpen);},[scheduleOpen,onSchedulePageChange]);
  useLayoutEffect(()=>()=>onSchedulePageChange?.(false),[onSchedulePageChange]);
  useLayoutEffect(()=>{if(scheduleOpen){scrollRegion?.reset();}},[scheduleOpen]);
  function openSchedule(setting:MedicationScheduleSetting){
    returnScroll.current=scrollRegion?.capture()??null;
    setSchedulePage({setting});
  }
  function closeSchedule(){
    const label=schedulePage?.setting==='frequency'?navigationLabels.frequency:navigationLabels.times;
    setSchedulePage(null);
    requestAnimationFrame(()=>{
      if(!surface.current)return;
      scrollRegion?.restore(returnScroll.current);
      focusWithoutScroll(surface.current.querySelector<HTMLElement>(`button[aria-label="${label}"]`));
    });
  }
  const scheduleBack=useRef<()=>Promise<void>>(async()=>{});
  scheduleBack.current=async()=>{if(!item||!canEdit||await editor.flush())closeSchedule();};
  useLayoutEffect(()=>{
    onNavigationChange?.(schedulePage?{title:schedulePage.setting==='frequency'?navigationLabels.frequency:navigationLabels.times,onBack:()=>void scheduleBack.current()}:null);
    return ()=>onNavigationChange?.(null);
  },[schedulePage,onNavigationChange]);
  if(schedulePage&&editor.kind==='plan')return <div ref={element=>{surface.current=element;}} className="medication-editor"><MedicationSchedulePage initialDraft={scheduleDrafts.current.get(schedulePage.setting)} onDraftChange={value=>{const key=schedulePage.setting;if(value===undefined)scheduleDrafts.current.delete(key);else scheduleDrafts.current.set(key,value);}} plan={editor.draft} setting={schedulePage.setting} disabled={!canEdit} onBack={closeSchedule} saveError={editor.error} onSave={()=>item?editor.flush():Promise.resolve(true)} onChange={schedule=>{editor.change({schedule});}}/></div>;
  return <form id={formId} ref={element=>{surface.current=element;}} onCompositionStart={()=>editor.compose(true)} onCompositionEnd={()=>editor.compose(false)} className="medical-log-editor medication-editor" onSubmit={e=>{e.preventDefault();void editor.flush(true);}} onBlur={()=>{if(item)void editor.flushOnBlur();}}>
    {editor.kind==='plan'?<MedicationPlanIdentity member={member} identity={editor.identity} medicationId={editor.draft.medication_id||null} canEdit={canEdit} onChange={editor.selectMedication}/>:<div className={item?'report-overview-layout medication-overview':undefined}>
      {item?<MedicationSources member={member} item={item} canEdit={informationEditable} onReload={onReload}/>:null}
      <div className="report-basic-information"><Group title="药品信息">
        <MedicationIdentityFields identity={editor.draft} creating={!item} canEdit={informationEditable} onChange={editor.change}/>
        <Choice<MedicationPrescriptionType> label="处方类型" value={editor.draft.prescription_type} choices={{unknown:'未确认',prescription:'处方药',nonprescription:'非处方药'}} disabled={!informationEditable} onChange={v=>editor.change({prescription_type:v})}/>
        <NotesField value={editor.draft.notes} disabled={!informationEditable} onChange={v=>editor.change({notes:v||null})}/>
        {catalogMode?<label className="field-row"><span className="field-label">说明书链接</span><input aria-label="说明书链接" value={editor.draft.leaflet_url??''} onChange={event=>editor.change({leaflet_url:event.target.value||null})}/></label>:null}
        {editor.draft.leaflet_url?<a className="control control--row grouped-list-create-button medication-leaflet-row" href={editor.draft.leaflet_url} target="_blank" rel="noreferrer">查看说明书</a>:item?.sources?.some(f=>f.purpose==='leaflet')?<a className="control control--row grouped-list-create-button medication-leaflet-row" href={medicationSourceUrl(member,String(item.medication_id),item.sources.find(f=>f.purpose==='leaflet')!.resource_id)} target="_blank" rel="noreferrer">查看说明书</a>:null}
      </Group></div>
    </div>}
    {editor.kind==='plan'?<MedicationPlanFields plan={editor.draft} onOpenSetting={openSchedule} disabled={!canEdit} onChange={editor.change}><NotesField value={editor.draft.notes} disabled={!canEdit} onChange={v=>editor.change({notes:v||null})}/></MedicationPlanFields>:null}
    {item&&kind==='medication'&&!catalogMode?<MedicationExtras member={member} onReload={onReload} beforeDelete={editor.flush} item={item} canEdit={canEdit} onSelectionChange={setBatchSelectionMode} onOpenBatch={async id=>{if(await editor.flush())onOpenBatch?.(id);}}/>:null}
    {editor.error?<div role="alert"><p>{editor.error}</p>{item&&canEdit?<button className="control" type="button" onClick={()=>void editor.flush()}>重试保存</button>:null}</div>:null}
    {editor.dirty||editor.saving?<p role="status" className="content-description">{editor.saving?'正在保存…':'尚未保存'}</p>:null}
    {item&&canEdit&&(kind==='plan'||catalogMode)&&!batchSelectionMode?<button className="control control--secondary control--danger report-delete-button destructive-action-button removal-action-control" type="button" onClick={()=>void editor.remove()} disabled={editor.saving}><TrashIcon/>删除{kind==='medication'?'药品':'用药计划'}</button>:null}
  </form>;
}
