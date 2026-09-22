import type {MemoryReference} from "../../api/memory/memoryApi";
import {GroupedList} from '../../components/GroupedList';
import {SettingsListForwardIcon} from '../settings/SettingsPrimitives';
import {kindLabels} from './memoryPresentation';


function ReferenceLinks({references,onRead}:{references:MemoryReference[];onRead:(reference:MemoryReference)=>void}){
  const totals=new Map<string,number>(),seen=new Map<string,number>();
  for(const reference of references)totals.set(reference.object_type,(totals.get(reference.object_type)||0)+1);
  return <GroupedList density="standard" className="memory-evidence-links">{references.map(reference=>{
    const kind=reference.object_type,index=(seen.get(kind)||0)+1;seen.set(kind,index);
    return <button className="control control--row memory-navigation-row" type="button" key={JSON.stringify(reference)} onClick={()=>onRead(reference)}><span>
      查看{kindLabels[kind]||'详情'}{reference.version?` · 第 ${reference.version} 版`:''}{totals.get(kind)!>1?` · ${index}`:''}
    </span><SettingsListForwardIcon/></button>;
  })}</GroupedList>;
}

export function MemoryReferences({references,onRead}:{references:MemoryReference[];onRead:(reference:MemoryReference)=>void}){
  return <>
    {references.length?<section className="memory-evidence"><h4>关联内容</h4><ReferenceLinks references={references} onRead={onRead}/></section>:null}
  </>;
}
