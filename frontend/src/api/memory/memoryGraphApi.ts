import {request} from "../transport/request";
import type {MemoryObject,MemoryReadQuery,MemoryReference,MemoryTime} from './memoryApi';
export type MemoryGraphQuery=MemoryReadQuery&{episode_id?:string;edge_limit?:number;edge_cursor?:string};
export type MemoryGraphEdge={edge_kind:'stored_reference'|'event_relation';from:MemoryReference;to:MemoryReference;
 relation?:MemoryReference;basis?:MemoryReference;field_path?:string;relation_type?:string;direction?:'symmetric'|'from_to';valid_time?:MemoryTime;time_extent_unknown?:boolean};
export type MemoryGraphRead={member_id:string;record_cutoff:number;view:string;nodes:MemoryReference[];objects:MemoryObject[];edges:MemoryGraphEdge[];
 next_cursor:string|null;next_edge_cursor:string|null;edge_continuation:MemoryGraphQuery|null;continuations:MemoryGraphQuery[];boundary_references:MemoryReference[];gaps:unknown[];unread:unknown[];complete:boolean};
export const readMemoryGraph=(member:string,values:MemoryGraphQuery,signal?:AbortSignal)=>request<MemoryGraphRead>(`/members/${encodeURIComponent(member)}/memory/graph`,{method:'POST',body:JSON.stringify(values),signal});
