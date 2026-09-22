import type {ReactNode} from 'react';
import type {MemoryObject, MemoryReference} from "../../api/memory/memoryApi";
import {GroupedList, ReadonlyField} from '../../components/GroupedList';
import {ChevronRightIcon} from '../../components/icons';
import {MemoryGaps} from './MemoryGaps';
import {asReference, memoryTimestamp, object, text} from './memoryPresentation';

export function MemoryEpisodeView({row,onRead,onGraph}:{row:MemoryObject;onRead:(reference:MemoryReference)=>void;onGraph?:(id:string,version?:number)=>void}) {
  const isEpisode = row.object_type === 'episode';
  const revision = isEpisode ? object(row.current_revision) : row;
  const group = (label:string, content:ReactNode) => <section aria-label={label}><h4>{label}</h4>{content}</section>;
  const versions = (Array.isArray(row.revisions)?row.revisions:[]).map(asReference).filter((ref):ref is MemoryReference=>Boolean(ref)).reverse();
  return <article className="memory-entry memory-episode-detail">
    {isEpisode?group('事项范围',<p className="memory-prose">{text(row.scope)}</p>):null}
    {Object.keys(revision).length ? <>
      {group('事项经过',<p className="memory-prose">{text(revision.summary)}</p>)}
      {group(isEpisode?'当前状态':'当时状态',<p className="memory-prose">{text(revision.state)}</p>)}
      {group('更新说明',<p className="memory-prose">{text(revision.reason)}</p>)}
      <GroupedList density="standard" layout="fields"><ReadonlyField label="版本" value={`第 ${revision.version} 版`}/><ReadonlyField label="保存时间" value={memoryTimestamp(revision.submitted_at)}/></GroupedList>
    </>:<p role="status">事项摘要与状态尚未生成，或当前不可读取。</p>}
    {onGraph&&text(row.episode_id)?<GroupedList density="standard"><button type="button" className="control control--row memory-navigation-row" onClick={()=>onGraph(text(row.episode_id),isEpisode?undefined:Number(row.version))}><span>查看事项图谱</span><ChevronRightIcon/></button></GroupedList>:null}
    {versions.length?group('变更历史',<GroupedList density="standard">{versions.map(ref=><button key={ref.version} type="button" className="control control--row memory-navigation-row" onClick={()=>onRead(ref)}><span>第 {ref.version} 版{ref.version===revision.version?'（当前）':''}</span><ChevronRightIcon/></button>)}</GroupedList>):null}
    <MemoryGaps label="未读范围" values={row.unread} onRead={onRead}/><MemoryGaps label="资料缺口" values={row.gaps} onRead={onRead}/>
  </article>;
}
