import {useEffect,useId,useRef,useState} from 'react';
import type {Medication,MedicationItem} from '../../api/medicationTypes';
import {listMedicationCatalog,readMedicationCatalog} from '../../api/medicationApi';
import {MedicationEditor} from '../medications/MedicationEditor';
import {medicationName,medicationSpecification} from '../medications/medicationPresentation';
import {SettingsListPanel,SettingsListForwardIcon} from './SettingsPrimitives';
import {SettingsDetailPanel} from './SettingsDetailPanel';
import {PlusIcon} from '../../components/icons';
import {ListCount} from '../../components/ListCount';
import {GroupedList} from '../../components/GroupedList';
import {ContentDialog} from '../../components/ContentDialog';
import {EmptyState} from '../../components/EmptyState';
import {saveBeforeNavigation} from '../../utils/pendingNavigation';
import '../../styles/medications.css';

export function MedicationCatalogSettings({detailOpen,onOpenDetail,onCloseDetail}:{detailOpen:boolean;onOpenDetail:()=>void;onCloseDetail:()=>void}) {
  const [items,setItems]=useState<Medication[]>([]),[selected,setSelected]=useState<Medication|null>(null);
  const [id,setId]=useState(''),[query,setQuery]=useState(''),[cursor,setCursor]=useState<string|null>(null);
  const [total,setTotal]=useState(0);
  const [error,setError]=useState(''),[loading,setLoading]=useState(false),[refresh,setRefresh]=useState(0);
  const [creating,setCreating]=useState(false),[saving,setSaving]=useState(false);
  const formId=useId(),listTitleId=useId(),current=useRef('');current.current=id;
  useEffect(()=>{
    const controller=new AbortController();setLoading(true);setError('');
    void listMedicationCatalog(query,undefined,controller.signal).then(result=>{setItems(result.items);setTotal(result.total);setCursor(result.next_cursor);})
      .catch(cause=>{if(!controller.signal.aborted){setItems([]);setTotal(0);setCursor(null);setError(cause.message);}})
      .finally(()=>{if(!controller.signal.aborted)setLoading(false);});
    return()=>controller.abort();
  },[query,refresh]);
  useEffect(()=>{
    const controller=new AbortController();setSelected(null);
    if(id)void readMedicationCatalog(id,controller.signal).then(setSelected).catch(cause=>{if(!controller.signal.aborted)setError(cause.message);});
    return()=>controller.abort();
  },[id]);
  async function reload(){const expected=id;try{const item=await readMedicationCatalog(expected);if(current.current===expected)setSelected(item);}catch(cause){if(current.current===expected)setError(cause instanceof Error?cause.message:'药品读取失败');}}
  async function more(){if(!cursor||loading)return;setLoading(true);try{const result=await listMedicationCatalog(query,cursor);setItems(value=>[...value,...result.items]);setCursor(result.next_cursor);}catch(cause){setError(cause instanceof Error?cause.message:'药品读取失败');}finally{setLoading(false);}}
  function saved(value:MedicationItem){if(value.medication_plan_id!==undefined)return;setId(value.medication_id);setSelected(value);setCreating(false);setRefresh(v=>v+1);onOpenDetail();}
  async function closeDetail(){if(await saveBeforeNavigation())onCloseDetail();}
  return <>
    <SettingsListPanel className="dictionary-list-column" bodyClassName="dictionary-list-body" title="药品目录" titleId={listTitleId}>
      <div className="dictionary-list-tools">
        <input type="search" aria-label="搜索药品目录" placeholder="搜索药名或规格" value={query} onChange={event=>setQuery(event.target.value)}/>
      </div>
      <div className={`dictionary-entity-list${!loading&&!items.length?' empty':''}`} aria-busy={loading}>
        <GroupedList className="dictionary-grouped-list" density="standard">
          <button className="control control--row dictionary-create-button grouped-list-create-button" type="button" disabled={saving} onClick={async()=>{if(await saveBeforeNavigation())setCreating(true);}}>
            <PlusIcon className="settings-action-icon"/><span>添加药品</span>
          </button>
          {items.map(item=><button className="dictionary-entity-row dictionary-medication-row" type="button" key={item.medication_id} aria-current={detailOpen&&id===item.medication_id?'page':undefined} onClick={async()=>{if(await saveBeforeNavigation()){setId(item.medication_id);onOpenDetail();}}}>
            <span><strong>{medicationName(item)}</strong></span>
            <small title={medicationSpecification(item)}>{medicationSpecification(item)||'规格未记录'}</small>
            <SettingsListForwardIcon className="dictionary-row-chevron"/>
          </button>)}
        </GroupedList>
        {loading?<p className="status-message">正在读取药品目录…</p>:!items.length&&!error?<EmptyState className="dictionary-empty-state" role="status" title={query?'没有匹配的药品':'暂无药品'}/>:null}
        {!loading&&items.length?<ListCount total={total} unit="种" label="药品"/>:null}
        {cursor?<button className="control" type="button" disabled={loading} onClick={()=>void more()}>加载更多</button>:null}
        {error?<p role="alert">{error}<button type="button" className="control" onClick={()=>{setRefresh(v=>v+1);if(id)void reload();}}>重试</button></p>:null}
      </div>
    </SettingsListPanel>
    <SettingsDetailPanel title={selected?medicationName(selected):'药品目录'} mobileOpen={detailOpen} onBack={()=>void closeDetail()} wide>
      {selected?<MedicationEditor key={id} catalogMode member="" kind="medication" item={selected} canEdit onSaved={saved} onDeleted={()=>{setId('');setSelected(null);setRefresh(v=>v+1);onCloseDetail();}} onReload={()=>void reload()}/>:<EmptyState title={id?'正在读取…':'选择药品查看信息'}/>}
    </SettingsDetailPanel>
    {creating?<ContentDialog title="添加药品" creation busy={saving} onClose={()=>setCreating(false)} actions={<button type="submit" form={formId} className="control control--primary" disabled={saving}>完成</button>}>
      <MedicationEditor catalogMode member="" kind="medication" item={null} canEdit formId={formId} onSavingChange={setSaving} onSaved={saved} onDeleted={()=>{}} onReload={()=>{}}/>
    </ContentDialog>:null}
  </>;
}
