import { request } from "../transport/request";
import type { ModelRetry } from "../models/modelRetryTypes";

export type MemoryReference = { object_type: string; object_id: string; version?: number | null; item_id?: string | null };
export type MemoryTime = { start?: { value: string; precision: string } | null; end?: { value: string; precision: string } | null; uncertainty?: string; unknown?: string[] };
export type MemoryEventAssociation = {event_id: string; entity_id: string; description: string};
export type MemoryObject = Record<string, unknown> & { object_type: string; title?: string; description?: string; state?: string; summary?: string | null; content?: string; event_associations?: MemoryEventAssociation[] };
export const memoryCategories = {
  member_profile: "成员基本信息（包括既往史）", body_metric: "身体指标", medical_report: "医疗报告",
  medical_log: "健康日记", medication: "用药记录"
};
export type MemoryCategory = keyof typeof memoryCategories;
export type MemorySettings = {
  member_id: string; formation_state: "disabled" | "enabled" | "paused"; source_categories: MemoryCategory[];
  setting: { setting_id: string } | null; can_manage: boolean; can_append: boolean;
};
export type MemoryChangeReference = {source_database: string; change_id: string; field_path?: string | null};
export type MemoryRead = {
  business_changes?: (MemoryChange & {field_path: string; title: string; content_text: string})[];
  member_id: string; record_cutoff: number; objects: MemoryObject[]; view: string; target_time: MemoryTime | null;
  next_cursor: string | null; coverage: { matching_objects: number; returned_objects: number; complete: boolean };
  gaps: unknown[]; unread: unknown[]; settings: MemorySettings;
};
export type MemoryReadQuery = {
  business_changes?: MemoryChangeReference[];
  object_types?: string[]; references?: MemoryReference[]; query?: string; target_time?: MemoryTime;
  view?: "current" | "historical_saved"; record_cutoff?: number; cursor?: string; limit?: number;
};
const base = (member: string) => `/members/${encodeURIComponent(member)}/memory`;
export const readMemory = (member: string, input: MemoryReadQuery, signal?: AbortSignal) =>
  request<MemoryRead>(`${base(member)}/reading`, { method: "POST", body: JSON.stringify(input), signal });
export type MemoryProcessingSummary = MemoryObject & {
  group_id: string;
  change: (Pick<MemoryChange, 'source_database' | 'change_id' | 'resource_type' | 'resource_id' | 'operation_kind' | 'recorded_at'> & {title: string | null}) | null;
  event_count: number;
  processing_status: string;
  completed_tasks: number;
  total_tasks: number;
  submitted_at: string;
};
export type MemoryRecoveryRecord = {
  recovery_id: string; account_id: string; member_id: string; attempt_id: string; operation_id: string;
  kind: 'auto'|'explicit'; recorded_at: string; retry_epoch: number;
  checkpoint: unknown;
};
export type MemoryProcessingAttempt = MemoryObject & {
  object_type: 'processing_attempt'; attempt_id: string; previous_attempt_id: string | null;
  processing_status: 'pending'|'running'|'completed'|'failed'|'cancelled'|null;
  input_references: MemoryReference[]; result_references: MemoryReference[];
  error_code: string|null; error_message: string|null; outcome_reason: string|null; gaps: string[];
  model_id: string|null;
  commit_id: string; started_commit_id: string|null; updated_commit_id: string; updated_at: string;
  entry_references: MemoryReference[]; restricted_entries: number;
  available_actions: {resume: boolean; retry: boolean; cancel: boolean};
  checkpoint: Record<string, unknown> | null; recovery_status: string | null; recovery_reason: string | null;
  recovery_records: MemoryRecoveryRecord[];
};
export type MemoryProcessingGroup = MemoryProcessingSummary & {
  group_id: string;
  change: (Pick<MemoryChangeDetail, 'source_database' | 'change_id' | 'resource_type' | 'resource_id' | 'operation_kind' | 'recorded_at' | 'fields'> & {title: string | null}) | null;
  events: MemoryObject[];
  records: MemoryObject[];
  processing_status: string;
  completed_tasks: number;
  total_tasks: number;
  submitted_at: string;
};
export const getMemorySettings = (member: string, signal?: AbortSignal) => request<MemorySettings>(`${base(member)}/settings`, {signal});
export const saveMemorySettings = (member: string, input: {operation_id:string;previous_setting_id:string|null;formation_state:MemorySettings['formation_state'];source_categories:MemoryCategory[]}) => request<MemorySettings>(`${base(member)}/settings`,{method:'PUT',body:JSON.stringify(input)});
export const retryMemoryProcessing = (member: string, attempt: string, operation: string) => request(`${base(member)}/processing/${encodeURIComponent(attempt)}/retry`, {method:"POST",body:JSON.stringify({operation_id:operation})});
export const resumeMemoryProcessing = (member: string, attempt: string, operation: string) => request<MemoryProcessingAttempt>(`${base(member)}/processing/${encodeURIComponent(attempt)}/resume`, {method:"POST",body:JSON.stringify({operation_id:operation})});
export const cancelMemoryProcessing = (member: string, attempt: string) => request(`${base(member)}/processing/${encodeURIComponent(attempt)}/cancel`, {method:"POST"});

export type MemoryStatus = 'not_included'|'skipped'|'pending'|'processing'|'failed'|'completed_empty'|'generated';
export type MemoryChange = {
  change_id: string; source_database: string; resource_type: string; resource_id: string;
  operation_kind: string; recorded_at: string; memory_status: MemoryStatus;
  processing: MemoryProcessingSummary | null;
};
export type MemoryChangePage = {changes: MemoryChange[]; next_cursor: string | null};
export type MemoryChangeTarget = {resource_type: 'member' | 'medical_history' | 'medical_log' | 'report' | 'medication_plan' | 'body_record'; resource_id: string}
  | {resource_type: 'medication_batch'; resource_id: string; medication_id: string};
export type MemoryProcessingStep = {attempt_id:string|null;receipt_id?:string;progress_id:string;step_id:string;parent_step_id:string|null;status:'running'|'retrying'|'completed'|'failed'|'skipped';details:Record<string,unknown>&{retry?:ModelRetry;timing?:{started_at:string;finished_at:string|null;elapsed_seconds:number}};error_code:string|null;error_message:string|null;submitted_at:string;record_sequence:number};
export type MemoryRelationResult = {attempt_id:string;record_cutoff:number;relations:MemoryObject[];events:MemoryObject[]};
export type MemoryModelInput = {attempt_id:string;entry_id:string;model_id:string;call_number:number;submitted_at:string;content:unknown;retry?:ModelRetry;kind?:string;output?:(Record<string,unknown>&{retry?:ModelRetry})|null;output_revision?:string|null;output_entry_sequence?:number|null;processing_step?:string|null;status?:string;error_code?:string|null};
export type MemoryToolDelta = {index:number;id:string;name_delta:string;arguments_delta:string};
export type MemoryModelFragment = {entry_id:string;entry_sequence:number;stream_sequence:number;received_at:string;
  delta:{content_delta?:string;reasoning_delta?:string;raw_content_delta?:string;tool_call_deltas?:MemoryToolDelta[];usage?:Record<string,unknown>;stop_reason?:string|null}};
export type MemoryModelFragments = {fragments:MemoryModelFragment[];next_entry_sequence:number;has_more:boolean;
  status:string;output_revision:string|null;content_available:boolean;access_revision:string};
export type MemoryChangeDetail = Omit<MemoryChange, 'processing'> & {
  relation_results: MemoryRelationResult[];
  processing: MemoryProcessingGroup | null;
  processing_steps: MemoryProcessingStep[];
  model_inputs: MemoryModelInput[];
  extraction_results: {attempt_id:string;events:MemoryObject[];entities:MemoryObject[];vectors:{binding_id:string;vector_id:string;event_id:string;entity_id:string|null;name_id:string|null;index_kind:string;content_text:string;space_id:string;model_id:string;dimensions:number;status:{state:string;error_message?:string|null}|null}[]}[];
  access_revision: string;
  content_available: boolean;
  content_text: string | null;
  targets: MemoryChangeTarget[];
  fields: {field_path: string; after_exists: boolean; after_value: unknown}[];
};
export const readMemoryChanges = (member: string, cursor?: string, signal?: AbortSignal) =>
  request<MemoryChangePage>(`${base(member)}/changes${cursor ? `?cursor=${encodeURIComponent(cursor)}` : ''}`, {signal});
export const readMemoryChangeSummaries = (member:string, changes:MemoryChange[], signal?:AbortSignal) =>
  request<{changes:Pick<MemoryChange,'source_database'|'change_id'|'memory_status'|'processing'>[]}>(`${base(member)}/changes/summaries`,
    {method:'POST',body:JSON.stringify({references:changes.map(({source_database,change_id})=>({source_database,change_id}))}),signal});
export const readMemoryChange = (member: string, change: MemoryChange, signal?: AbortSignal) =>
  request<MemoryChangeDetail>(`${base(member)}/changes/${encodeURIComponent(change.source_database)}/${encodeURIComponent(change.change_id)}`, {signal});

const changePath = (member:string, change:Pick<MemoryChange,'source_database'|'change_id'>) =>
  `${base(member)}/changes/${encodeURIComponent(change.source_database)}/${encodeURIComponent(change.change_id)}`;
export type MemoryChangeStatus = Pick<MemoryChangeDetail,'memory_status'|'content_available'|'access_revision'|'processing'|'processing_steps'|'model_inputs'>;
export type MemoryStepContent = Pick<MemoryChangeDetail,'access_revision'|'content_available'|'processing_steps'|'model_inputs'>;
export const readMemoryChangeStatus = (member:string, change:MemoryChange, signal?:AbortSignal) =>
  request<MemoryChangeStatus>(`${changePath(member,change)}/status`,{signal});
export const readMemoryStep = (member:string, change:MemoryChange, step:string, parent:string|null, signal?:AbortSignal) =>
  request<MemoryStepContent>(`${changePath(member,change)}/steps/${encodeURIComponent(step)}${parent?`?parent_step_id=${encodeURIComponent(parent)}`:''}`,{signal});
export const readMemoryModel = (member:string, change:MemoryChange, entry:string, signal?:AbortSignal) =>
  request<Pick<MemoryChangeDetail,'access_revision'|'content_available'|'model_inputs'>>(`${changePath(member,change)}/models/${encodeURIComponent(entry)}`,{signal});
export const readMemoryModelFragments = (member:string, change:MemoryChange, entry:string, after:number, signal?:AbortSignal) =>
  request<MemoryModelFragments>(`${changePath(member,change)}/models/${encodeURIComponent(entry)}/fragments?after_entry_sequence=${after}&limit=200`,{signal});
