import { ScrollRegion } from "../../components/ScrollRegion";
import { ListSelectionSlot } from "../../components/ListSelectionSlot";
import { navigationLabels } from "../../components/navigationLabels";
import { EmptyState } from "../../components/EmptyState";
import {useEffect,useId,useRef,useState,type ReactNode} from 'react';
import type {Member} from '../../api/memberApi';
import type {MedicationFilters,MedicationItem,MedicationSection} from '../../api/medicationTypes';
import {listMedications,readMedication,deleteMedication} from '../../api/medicationApi';
import {type RoutePath,medicationPath,medicationBatchPath,medicationRoute,healthPathForMember,medicalLogPath} from '../../app/routes';
import {HealthMemberOverview} from '../members/HealthMemberOverview';
import {MemberInformationPanel} from '../members/MemberInformationPanel';
import {WorkspaceToolbar} from '../../components/WorkspaceToolbar';
import {GroupedList} from '../../components/GroupedList';
import {PlusIcon,ChevronRightIcon,FilterIcon,SearchIcon,CalendarIcon,MedicineBoxIcon} from '../../components/icons';
import {DateField} from '../../components/DateField';
import {SelectPopover} from '../../components/SelectPopover';
import {saveBeforeNavigation} from '../../utils/pendingNavigation';
import {focusWithoutScroll} from '../../utils/inputMethod';
import {MedicationBatchCreateDialog} from './MedicationBatchCreateDialog';
import {MedicationBatchPanel} from './MedicationBatchPanel';
import {MedicationEditor,type MedicationEditorHandle} from './MedicationEditor';
import {ListCount} from '../../components/ListCount';
import {useListDeleteActions} from '../../components/useListDeleteActions';
import {useActiveScope} from '../../utils/useActiveScope';
import {MedicationCreateDialog,type MedicationNavigation} from './MedicationCreateDialog';
import {sectionKinds,sectionLabels,itemId,itemName,statusLabels,planSummary,medicationSpecification} from './medicationPresentation';
import '../../styles/medical-logs.css';
import '../../styles/medications.css';
import { captureAuthContext, isAuthContextCurrent, subscribeAuthLifecycle } from '../../api/authLifecycle';

const positions=new Map<string,{filters:MedicationFilters;scroll:number}>();
subscribeAuthLifecycle(() => positions.clear());
const emptyFilters=(section:MedicationSection):MedicationFilters=>({query:'',status:section==='plans'?'ongoing':'',after_date:'',before_date:'',undated:false,...(section==='catalog'?{inventory_only:true}:{})});
type MedicationWorkspaceProps={member:Member;route:RoutePath;navigate:(p:RoutePath,replace?:boolean)=>void;sidebarToggle:ReactNode};
export function MedicationWorkspace(props:MedicationWorkspaceProps) {
  return <MedicationSectionWorkspace key={`${props.member.member_id}:${medicationRoute(props.route)!.section}`} {...props}/>;
}
function MedicationSectionWorkspace({member,route,navigate,sidebarToggle}:MedicationWorkspaceProps) {
  const parsed=medicationRoute(route)!;const section=parsed.section;const kind=sectionKinds[section];const selectedId=parsed.id;
  const auth = captureAuthContext();
  const scope=auth.accountId+':'+auth.generation+':'+member.member_id+':'+section;
  const contentLabel=kind==='medication'?'药品':sectionLabels[section];
  const [createBatch,setCreateBatch]=useState(false);
  const [batchTarget,setBatchTarget]=useState<string>();
  const [scheduleOpen,setScheduleOpen]=useState(false);
  const [createMethod,setCreateMethod]=useState(false);
  const createFormId=useId();
  const [detailNavigation,setDetailNavigation]=useState<MedicationNavigation|null>(null);
  const [createNavigation,setCreateNavigation]=useState<MedicationNavigation|null>(null);
  const [createSaving,setCreateSaving]=useState(false);
  const [filterMode,setFilterMode]=useState<'status'|'search'|'date'>('status');
  const [total,setTotal]=useState(0);const [deleteError,setDeleteError]=useState('');
  const editor=useRef<MedicationEditorHandle>(null);
  const detailScroll=useRef<HTMLDivElement>(null);
  const isCurrent=useActiveScope(scope);
  const currentId=useRef(selectedId);currentId.current=selectedId;
  const editable=useRef(member.can_edit);editable.current=member.can_edit;
  const [items,setItems]=useState<MedicationItem[]>([]);const [selected,setSelected]=useState<MedicationItem|null>(null);const [creating,setCreating]=useState(false);const [information,setInformation]=useState(false);
  const [filters,setFilters]=useState<MedicationFilters>(()=>positions.get(scope)?.filters??emptyFilters(section));const [cursor,setCursor]=useState<string|null>(null);const [error,setError]=useState('');const [detailError,setDetailError]=useState('');const [detailLoading,setDetailLoading]=useState(false);const [loading,setLoading]=useState(false);const [refresh,setRefresh]=useState(0);
  const list=useRef<HTMLDivElement>(null);const generation=useRef(0);const detailGeneration=useRef(0);const detailPanel=useRef<HTMLElement|null>(null);const returnFocus=useRef<HTMLElement|null>(null);const active=useRef(true);const stored=useRef({filters,scroll:positions.get(scope)?.scroll??0});
  const loadedCount=useRef(items.length);loadedCount.current=items.length;
  const catalogFilters=useRef(filters);
  stored.current.filters=filters;
  useEffect(()=>{active.current=true;return()=>{active.current=false;if(isAuthContextCurrent(auth))positions.set(scope,stored.current);};},[scope]);
  useEffect(()=>{if(!member.can_edit){setCreateMethod(false);setCreating(false);}},[member.can_edit]);
  useEffect(()=>{const controller=new AbortController();const token=++generation.current;setLoading(true);setError('');
    const retainCount=catalogFilters.current===filters?loadedCount.current:0;catalogFilters.current=filters;
    void listMedications(member.member_id,kind,filters,undefined,controller.signal).then(async r=>{
      const rows=[...r.items];
      while(rows.length<retainCount&&r.next_cursor){
        if(controller.signal.aborted||token!==generation.current)return;
        r=await listMedications(member.member_id,kind,filters,r.next_cursor,controller.signal);
        rows.push(...r.items.filter(item=>!rows.some(existing=>itemId(existing,kind)===itemId(item,kind))));
      }
      if(controller.signal.aborted||token!==generation.current)return;setItems(rows);setTotal(r.total);setCursor(r.next_cursor);requestAnimationFrame(()=>{if(active.current&&list.current)list.current.scrollTop=stored.current.scroll;});}).catch(e=>{if(!controller.signal.aborted&&token===generation.current){setItems([]);setTotal(0);setCursor(null);setError(e.message);}}).finally(()=>{if(!controller.signal.aborted&&token===generation.current)setLoading(false);});return()=>{controller.abort();generation.current++;};},[member.member_id,kind,filters,refresh]);
  useEffect(()=>{
    const controller=new AbortController();const token=++detailGeneration.current;
    setSelected(null);setDetailError('');setDetailLoading(!!selectedId);setInformation(false);
    if(selectedId)void readMedication(member.member_id,kind,selectedId,controller.signal)
      .then(item=>{if(!controller.signal.aborted&&token===detailGeneration.current)setSelected(item);})
      .catch(error=>{if(!controller.signal.aborted&&token===detailGeneration.current)setDetailError(error.message||'当前记录不可访问');})
      .finally(()=>{if(!controller.signal.aborted&&token===detailGeneration.current)setDetailLoading(false);});
    return()=>controller.abort();
  },[member.member_id,kind,selectedId]);
  useEffect(()=>{const reload=()=>setRefresh(v=>v+1);window.addEventListener('focus',reload);return()=>window.removeEventListener('focus',reload);},[]);
  async function open(id?:string,source?:HTMLElement){if(!await saveBeforeNavigation())return;if(source)returnFocus.current=source;setCreating(false);setInformation(false);navigate(medicationPath(member.member_id,section,id));}
  async function switchSection(next:MedicationSection){if(!await saveBeforeNavigation())return;positions.set(scope,stored.current);setCreating(false);setSelected(null);setInformation(false);navigate(medicationPath(member.member_id,next));}
  async function switchPlanStatus(status:string){if(!await saveBeforeNavigation())return;stored.current.scroll=0;setItems([]);setFilters({...filters,status,undated:status==='undated'});setCreating(false);setInformation(false);navigate(medicationPath(member.member_id,section));}
  async function more(){if(!cursor||loading)return;const token=generation.current;setLoading(true);try{const r=await listMedications(member.member_id,kind,filters,cursor);if(token===generation.current){setItems(v=>[...v,...r.items.filter(item=>!v.some(existing=>itemId(existing,kind)===itemId(item,kind)))]);setTotal(r.total);setCursor(r.next_cursor);}}catch(e){if(token===generation.current)setError(e instanceof Error?e.message:'目录读取失败');}finally{if(token===generation.current)setLoading(false);}}
  function saved(item:MedicationItem){if(!active.current)return;setSelected(item);if(kind==='plan'&&creating){const status=item.time_status||'undated';setFilters(v=>({...v,status,undated:status==='undated'}));}setRefresh(v=>v+1);setItems(value=>{const id=itemId(item,kind);return value.map(v=>itemId(v,kind)===id?item:v);});if(creating){setCreating(false);setCreateMethod(false);setCreateSaving(false);navigate(medicationPath(member.member_id,section,itemId(item,kind)));}}
  const detailScope=useRef('');detailScope.current=scope+':'+selectedId;
  async function reloadDetail(){
    if(!selectedId)return;
    const expected=detailScope.current;const token=++detailGeneration.current;setDetailLoading(true);
    const isCurrent=()=>active.current&&expected===detailScope.current&&token===detailGeneration.current;
    try{const item=await readMedication(member.member_id,kind,selectedId);if(isCurrent()){setSelected(item);setDetailError('');}}
    catch(error){if(isCurrent())setDetailError(error instanceof Error?error.message:'记录读取失败');}
    finally{if(isCurrent()){setDetailLoading(false);setRefresh(value=>value+1);}}
  }
  function deleted(id:string){
    if(!isCurrent())return;
    generation.current++;setLoading(false);
    setItems(value=>value.filter(item=>itemId(item,kind)!==id));
    setTotal(value=>Math.max(0,value-1));
    if(currentId.current===id){setSelected(null);navigate(medicationPath(member.member_id,section));}
  }
  const actions=useListDeleteActions({
    scope,enabled:member.can_edit&&kind==='plan',label:contentLabel,countLabel:kind==='medication'?'种药品':'条用药计划',
    insetActions:true,entries:items.map(item=>({id:itemId(item,kind),name:itemName(item)})),
    onDelete:async ids=>{
      const failed:string[]=[];const errors:string[]=[];setDeleteError('');
      for(const id of ids){
        if(!isCurrent()||!editable.current||kind!=='plan')return ids;
        try{
          if(editor.current?.id===id){
            if(!await editor.current.remove()){failed.push(id);errors.push('当前'+contentLabel+'删除失败，请查看详情中的错误后重试。');}
          }else{
            if(currentId.current===id&&!await saveBeforeNavigation()){failed.push(id);errors.push('当前草稿未保存，请完成保存后重试。');continue;}
            if(!isCurrent()||!editable.current||kind!=='plan')return ids;
            await deleteMedication(member.member_id,kind,id);deleted(id);
          }
        }catch(cause){failed.push(id);errors.push(cause instanceof Error?cause.message:'删除失败，请重试。');}
      }
      if(isCurrent()){setDeleteError([...new Set(errors)].join(' '));setRefresh(value=>value+1);}
      return failed;
    }
  });
  const current=selected?.member_id===member.member_id&&itemId(selected,kind)===selectedId?selected:null;
  const detailOpen=!!selectedId||information;
  const titleItem=current??items.find(item=>itemId(item,kind)===selectedId);
  const title=parsed.batchId?'药品批次':titleItem?itemName(titleItem):kind==='plan'?'用药计划详情':'药品详情';
  const batchReturn=useRef({id:parsed.batchId,scroll:0});
  const previousBatch=useRef(parsed.batchId);
  function openBatch(id:string){if(id==='new'){setBatchTarget(selectedId);setCreateBatch(true);return;}batchReturn.current={id,scroll:detailScroll.current?.scrollTop??0};navigate(medicationBatchPath(member.member_id,selectedId!,id));}
  useEffect(()=>{
    const previous=previousBatch.current;previousBatch.current=parsed.batchId;
    if(previous===parsed.batchId)return;
    const frame=requestAnimationFrame(()=>{
      if(parsed.batchId)focusWithoutScroll(detailPanel.current);
      else if(previous){const scroll=detailScroll.current;if(scroll)scroll.scrollTop=batchReturn.current.scroll;focusWithoutScroll(detailPanel.current?.querySelector<HTMLElement>(`[data-medication-batch="${CSS.escape(batchReturn.current.id??previous)}"]`)??detailPanel.current);}
    });return()=>cancelAnimationFrame(frame);
  },[parsed.batchId]);
  const previousDetail=useRef({open:detailOpen,information});
  useEffect(()=>{
    const previous=previousDetail.current;previousDetail.current={open:detailOpen,information};
    if(previous.open===detailOpen&&previous.information===information)return;
    const frame=requestAnimationFrame(()=>{
      if(window.matchMedia('(max-width: 650px)').matches){
        if(detailOpen)focusWithoutScroll(detailPanel.current);
        else if(returnFocus.current?.isConnected)focusWithoutScroll(returnFocus.current);
      }else if(previous.information&&!information&&returnFocus.current?.isConnected)focusWithoutScroll(returnFocus.current);
    });
    return()=>cancelAnimationFrame(frame);
  },[detailOpen,information]);
  return <section className="reports-workspace medical-logs-workspace medication-workspace" data-detail-open={detailOpen?'true':'false'}><div className="report-browser-layout">
    <div className="report-library-column"><WorkspaceToolbar className="reports-list-toolbar" title={navigationLabels.health} showBack={false} leading={sidebarToggle}/>
      <HealthMemberOverview member={member} informationOpen={information} section="medications" onOpenInformation={async source=>{if(await saveBeforeNavigation()){returnFocus.current=source;setCreating(false);setInformation(true);}}} onSelectReports={()=>navigate(healthPathForMember(member.member_id))} onSelectMedicalLogs={()=>navigate(medicalLogPath(member.member_id))} onSelectMedications={()=>void switchSection('catalog')}
        reportArchive={<section className="report-library" aria-label="用药记录列表" onKeyDown={actions.onKeyDown}><div className="report-library-controls">
          <div className="medication-tabs" role="tablist" aria-label="用药内容">{(Object.keys(sectionLabels) as MedicationSection[]).map(s=><button key={s} type="button" role="tab" aria-selected={s===section} className="control" onClick={()=>void switchSection(s)}>{s==='catalog'?<MedicineBoxIcon/>:<CalendarIcon/>}<span>{sectionLabels[s]}</span></button>)}</div>
          <ListSelectionSlot active={actions.selectionMode} selection={actions.heading}>
          {kind==='plan'?<>
            <div className="medication-plan-filters" data-mode={filterMode}>
              {filterMode==='status'?<SelectPopover ariaLabel="用药计划状态" interactionOwner="self" menuWidth="trigger" menuAlign="start" value={filters.status} placeholder={statusLabels[filters.status]} options={['ongoing','upcoming','ended'].map(value=>({value,label:statusLabels[value]}))} onChange={switchPlanStatus}/>:<button className="control control--icon" type="button" aria-label="展开计划状态栏" title="展开计划状态栏" onClick={()=>setFilterMode('status')}><FilterIcon/></button>}
              {filterMode==='search'?<input aria-label="搜索用药资料" type="search" placeholder="搜索药名、规格或内容" value={filters.query} onChange={e=>setFilters({...filters,query:e.target.value})}/>:<button className="control control--icon" type="button" aria-label="展开搜索栏" title="展开搜索栏" onClick={()=>setFilterMode('search')}><SearchIcon/></button>}
              {filterMode==='date'?<div className="date-range-filter" role="group" aria-label="日期范围"><DateField compact label="起始日期" emptyLabel="不限" emptyOptionLabel="不限" value={filters.after_date||null} onChange={v=>setFilters({...filters,after_date:v||''})}/><span aria-hidden="true">至</span><DateField compact label="结束日期" emptyLabel="不限" emptyOptionLabel="不限" value={filters.before_date||null} onChange={v=>setFilters({...filters,before_date:v||''})}/></div>:<button className="control control--icon" type="button" aria-label="展开日期范围栏" title="展开日期范围栏" onClick={()=>setFilterMode('date')}><CalendarIcon/></button>}
            </div>
          </>:<input className="medication-search" aria-label="搜索用药资料" type="search" placeholder="搜索药名、规格或内容" value={filters.query} onChange={e=>setFilters({...filters,query:e.target.value})}/>}
          </ListSelectionSlot>
        </div><div className={`report-library-scroll scroll-content${!items.length ? " empty" : ""}`} ref={list} onScroll={e=>{stored.current.scroll=e.currentTarget.scrollTop;}} aria-busy={loading}>
          {error?<p role="alert">{error}<button className="control" type="button" onClick={()=>setRefresh(v=>v+1)}>重试</button></p>:null}
          {deleteError?<p role="alert">{deleteError}</p>:null}
          {!error&&!items.length?<EmptyState role={loading ? "status" : undefined} title={loading ? "正在读取…" : filters.query.trim()||filters.after_date||filters.before_date ? `没有匹配的${contentLabel}` : `暂无${kind==='plan'?(filters.undated?'日期未记录的计划':statusLabels[filters.status]+'的计划'):contentLabel}`} />:null}
          {items.length ? <GroupedList as="ul" density="standard" selectionMode={actions.selectionMode?'multiple':undefined} className="report-date-list" aria-label={sectionLabels[section]}>{items.map(item=><li className="report-timeline-row" key={itemId(item,kind)}><button {...actions.rowProps(itemId(item,kind))} className="report-timeline-item medical-log-list-item" data-interaction-owner="row" type="button" disabled={actions.busy} aria-haspopup={member.can_edit&&kind==='plan'&&!actions.selectionMode?'menu':undefined} role={actions.selectionMode?'checkbox':undefined} aria-checked={actions.selectionMode?actions.selected(itemId(item,kind)):undefined} aria-current={!actions.selectionMode&&!information&&itemId(item,kind)===selectedId?'page':undefined} onClick={event=>actions.selectionMode?actions.toggle(itemId(item,kind)):void open(itemId(item,kind),event.currentTarget)}>{actions.indicator(itemId(item,kind))}<span className="report-timeline-copy"><strong>{itemName(item)}</strong><span className="content-description">{kind==='medication'?medicationSpecification(item)||'规格未记录':planSummary(item)}</span></span>{!actions.selectionMode?<ChevronRightIcon className="report-timeline-chevron-icon"/>:null}</button></li>)}</GroupedList> : null}
          {items.length?<ListCount total={total} unit={kind==='medication'?'种':'条'} label={contentLabel}/>:null}
          {cursor?<button className="control medication-load-more" type="button" disabled={loading} onClick={()=>void more()}>加载更多</button>:null}
        </div>
        {actions.toolbar}
        {member.can_edit&&!actions.selectionMode?<div className="list-floating-actions report-library-floating-actions">
          <button className="control control--primary primary-action creation-action-button control-primary" type="button" aria-label={(kind==='plan'?navigationLabels.createPlan:'添加药品批次')} disabled={creating} onClick={async()=>{if(await saveBeforeNavigation()){if(kind==='medication'){setBatchTarget(undefined);setCreateBatch(true);}else{setInformation(false);setCreating(true);setCreateMethod(true);}}}}><PlusIcon/><span>{kind==='plan'?navigationLabels.createPlan:'添加药品批次'}</span></button>
        </div>:null}
        </section>}/>
    </div>
    <section className="report-detail-column medication-detail" data-schedule-open={scheduleOpen} aria-label="用药详情" ref={detailPanel} tabIndex={-1}>
      {information?<MemberInformationPanel key={member.member_id} member={member} onClose={()=>setInformation(false)}/>:parsed.batchId&&current&&!creating?<MedicationBatchPanel scrollRef={detailScroll} key={scope+':'+selectedId+':'+parsed.batchId} member={member.member_id} item={current} batchId={parsed.batchId} canEdit={member.can_edit&&!detailError} onClose={()=>navigate(medicationPath(member.member_id,section,selectedId))} onSaved={batch=>setSelected(value=>value&&value.medication_plan_id===undefined?{...value,batches:(value.batches??[]).some(b=>b.medication_batch_id===batch.medication_batch_id)?value.batches!.map(b=>b.medication_batch_id===batch.medication_batch_id?batch:b):[...(value.batches??[]),batch]}:value)} onDeleted={async()=>{await reloadDetail();navigate(medicationPath(member.member_id,section,selectedId));}}/>:<>
        <WorkspaceToolbar title={detailNavigation?.title??title} showBack={!!selectedId} onBack={detailNavigation?.onBack??(()=>void open(parsed.batchId?selectedId:undefined))}/>
        <ScrollRegion ref={detailScroll} className={`report-detail-scroll scroll-content content-column${!current||creating ? " empty" : ""}`} aria-busy={detailLoading}>
          {!creating&&current?<MedicationEditor ref={editor} onNavigationChange={setDetailNavigation} onSchedulePageChange={setScheduleOpen} key={scope+':'+selectedId} member={member.member_id} kind={kind} item={current} canEdit={member.can_edit&&!detailError} onSaved={saved} onDeleted={()=>{deleted(selectedId!);setRefresh(v=>v+1);}} onReload={()=>void reloadDetail()} onOpenBatch={openBatch}/>:!detailError?<EmptyState role={selectedId ? "status" : undefined} title={selectedId?'正在读取…':'选择一条记录查看详情'} />:null}
          {detailError?<div role="alert"><p>{detailError}</p><button className="control" type="button" disabled={detailLoading} onClick={()=>void reloadDetail()}>重新读取详情</button></div>:null}
        </ScrollRegion>
      </>}
    </section>
  </div>
    {actions.portal}
    {createBatch&&member.can_edit?<MedicationBatchCreateDialog member={member.member_id} medication={batchTarget} onClose={()=>setCreateBatch(false)} onSaved={batch=>{setCreateBatch(false);setRefresh(value=>value+1);navigate(medicationPath(member.member_id,'catalog',batch.medication_id));void reloadDetail();}}/>:null}
    {createMethod&&member.can_edit&&kind==='plan'?<MedicationCreateDialog formId={createFormId} navigation={createNavigation} saving={createSaving} onClose={()=>{setCreateMethod(false);setCreating(false);}}>
      {creating?<MedicationEditor formId={createFormId} onNavigationChange={setCreateNavigation} onSchedulePageChange={setScheduleOpen} member={member.member_id} kind={kind} item={null} canEdit={member.can_edit} onSavingChange={setCreateSaving} onSaved={saved} onDeleted={()=>{}} onReload={()=>{}}/>:null}
    </MedicationCreateDialog>:null}
  </section>;
}
