import {useEffect} from 'react';
import {useMemoryFilters} from './useMemoryFilters';
import {MemoryFilters} from './MemoryFilters';
import type {MemoryReadQuery, MemoryReference} from "../../api/memory/memoryApi";
import {MemoryGraph} from './MemoryGraph';
import {MemoryEpisodeGraph} from './MemoryEpisodeGraph';

export function MemoryGraphPane({accountId, memberId, accessRevision, episodeId, initialVersion, refresh, paused, onRead, onScopeChange, onMemberGraph}: {
  accountId: string | null; memberId: string; accessRevision: number; episodeId?: string; initialVersion?:number; refresh: number; paused: boolean;
  onRead: (reference: MemoryReference, related: MemoryReference[], scope: MemoryReadQuery) => void;
  onScopeChange: () => void; onMemberGraph: () => void;
}) {
  const storageKey = `serenita:memory-graph-filters:${accountId}:${memberId}`;
  const filters = useMemoryFilters(storageKey);
  const {query} = filters;
  useEffect(onScopeChange, [query, episodeId, initialVersion, refresh, onScopeChange]);

  if (episodeId) return <MemoryEpisodeGraph key={`${memberId}:${accessRevision}:${episodeId}:${initialVersion}`} memberId={memberId} accessRevision={accessRevision}
    episodeId={episodeId} initialVersion={initialVersion} refresh={refresh} paused={paused} onRead={onRead} onScopeChange={onScopeChange} onMemberGraph={onMemberGraph}/>;

  return <div className="memory-graph-pane">
    <MemoryGraph memberId={memberId} accessRevision={accessRevision} episodeId={episodeId} query={query} refresh={refresh} paused={paused || filters.invalid}
      onRead={onRead} onMemberGraph={onMemberGraph}/>
    <MemoryFilters state={filters} graph/>
  </div>;
}
