import { formatLocalDate } from "../../utils/localTime";
import type { MemoryObject, MemoryReference, MemoryTime, MemoryStatus } from "../../api/memory/memoryApi";

export const kindLabels: Record<string, string> = {
  episode: "事项", episode_revision: "事项版本", episode_membership: "事项归属",
  event: "事件", 
  processing_attempt: "处理记录",
  event_relation: "事件关系", memory_execution_entry:"执行记录",
  entity:"对象",entity_name:"对象名称",vector_space:"检索配置",vector_binding:"检索准备记录",vector_status:"检索准备进度",
};
export const memoryStatusLabels: Record<MemoryStatus, string> = {
  not_included: '不纳入记忆', skipped: '已跳过', pending: '待处理', processing: '处理中',
  failed: '处理失败', completed_empty: '处理完成，无新增记忆', generated: '已生成记忆',
};
export const statusLabels: Record<string, string> = {
  pending: "等待处理", running: "处理中", completed: "处理完成", failed: "处理失败", cancelled:"已取消"};
export const roleLabels: Record<string, string> = {actual_experience: "实际经历", recommendation: "建议", plan: "计划", user_statement: "用户陈述", reference_material: "外部参考资料", derived_interpretation: "派生认识", preference: "偏好", action_result: "执行结果", administrative_change: "资料管理变化"};
export const text = (value: unknown): string => typeof value === "string" ? value : "";
export const object = (value: unknown): Record<string, unknown> => value !== null && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : {};
export const objects = (value: unknown): Record<string, unknown>[] => Array.isArray(value) ? value.map(object) : [];
export const strings = (value: unknown): string[] => Array.isArray(value) ? value.filter((item): item is string => typeof item === "string") : [];
export function processingTaskTitle(row:MemoryObject):string {
  return ({intake_review:'接收变更',event_formation:'生成记忆',vector_index:'准备检索'} as Record<string,string>)[text(row.task_kind)] || '处理资料';
}
export function processingTaskDescription(row:MemoryObject):string {
  return ({intake_review:'记录已提交的变更，交给后台处理。',event_formation:'读取业务变更，提取事件与实体，通过事项范围检索并核对事项，保存每个事件的归属，再判断事项内事件关系并为每个新事件生成完整摘要与状态版本。',
    vector_index:'让已保存的事件能够被搜索到。'} as Record<string,string>)[text(row.task_kind)] || text(row.purpose);
}
export function processingError(status:Record<string,unknown>):string {
  return ({MEMORY_EXECUTION_INTERRUPTED:'上次处理已中断，未能完成。',MEMORY_SAG_IDENTITY_INVALID:'无法根据原文确认人物、药品等信息，已停止保存。',
    MEMORY_STAGE_OUTPUT_INVALID:'模型返回的内容不符合要求，多次修正后仍未通过检查。'} as Record<string,string>)[text(status.error_code)] || text(status.error_message);
}
export const memoryTimestamp = (value: unknown): string => text(value) ? formatLocalDate(text(value), true) : "未知";
export function memoryTime(value: unknown): string {
  const time = object(value) as MemoryTime;
  const bound = (value: NonNullable<MemoryTime["start"]>) => value.precision === "instant" ? memoryTimestamp(value.value) : value.value;
  if (time.start && time.end) return time.start.value === time.end.value ? bound(time.start) : `${bound(time.start)} 至 ${bound(time.end)}`;
  if (time.start) return `${bound(time.start)} 起；结束未知`;
  if (time.end) return `开始未知；截至 ${bound(time.end)}`;
  return "时间未知";
}
export function objectTitle(row: MemoryObject): string {
  if(row.object_type==='processing_attempt')return processingTaskTitle(row);
  if(row.object_type==='event')return text(row.title);
  if(row.object_type==='episode')return text(row.scope);
  if(row.object_type==='episode_revision')return `事项第 ${row.version} 版`;
  if(row.object_type==="event_relation")return "事件关系";
  const title=[row.title, row.name, row.description, row.summary, row.canonical_name, row.content, row.content_text, row.purpose,row.reason,objects(row.items)[0]?.content].map(text).find(Boolean);
  if(title)return title;
  return kindLabels[row.object_type] || row.object_type;
}
export function asReference(value: unknown): MemoryReference | null {
  const row = object(value);
  return typeof row.object_type === "string" && typeof row.object_id === "string" ? row as MemoryReference : null;
}
export function evidenceReferences(row: MemoryObject): MemoryReference[] {
  const result: MemoryReference[] = [];
  for (const field of ["dependencies", "supports", "counterevidence", "evidence", "revisions", "reading_entries", "result_references", "entry_references"])
    for (const raw of Array.isArray(row[field]) ? row[field] : []) { const reference = asReference(raw) || asReference(object(raw).reference); if (reference) result.push(reference); }
  if (row.object_type === "episode_membership") {
    if (text(row.event_id)) result.push({object_type: "event", object_id: text(row.event_id)});
    if (text(row.episode_id)) result.push({object_type: "episode", object_id: text(row.episode_id)});
  }
  const target = asReference(row.target); if (target) result.push(target);
  for(const value of objects(row.result_references)){const reference=asReference(value);if(reference)result.push(reference);}
  if(row.object_type==='processing_attempt'){
    if(text(row.previous_attempt_id))result.push({object_type:'processing_attempt',object_id:text(row.previous_attempt_id)});
  }
  if(row.object_type==='event'){
    for(const identity of strings(row.entity_ids))result.push({object_type:'entity',object_id:identity});
  }
  if(['vector_binding','vector_status'].includes(row.object_type)){
    if(text(row.binding_id)&&row.object_type==='vector_status')result.push({object_type:'vector_binding',object_id:text(row.binding_id)});
    if(text(row.event_id))result.push({object_type:'event',object_id:text(row.event_id)});
    if(text(row.space_id))result.push({object_type:'vector_space',object_id:text(row.space_id)});
    if(text(object(row.status).status_id))result.push({object_type:'vector_status',object_id:text(row.binding_id),item_id:text(object(row.status).status_id)});
  }

  if (row.object_type === "event_relation") {
    for (const field of ["from_event_id", "to_event_id"])
      if (text(row[field])) result.push({object_type:"event",object_id:text(row[field])});
  }
  if (text(row.attempt_id) && row.object_type !== "processing_attempt") result.push({object_type:"processing_attempt",object_id:text(row.attempt_id)});
  for (const raw of objects(row.related_references)) {const reference=asReference(raw);if(reference)result.push(reference);}
  const found = new Map<string, MemoryReference>();
  result.forEach(reference => found.set(`${reference.object_type}:${reference.object_id}:${reference.version ?? ""}:${reference.item_id ?? ""}`, reference));
  return [...found.values()];
}

export const eventRelationLabels:Record<string,string>={Continues:'延续',Supersedes:'更正',ConflictsWith:'冲突',Cancels:'取消',Duplicates:'重复',Supplements:'补充',Supports:'支持',Precedes:'先后',CausalClaim:'因果陈述',Contains:'包含'};
export function eventRelationLabel(relationType:unknown):string {
  return eventRelationLabels[text(relationType)]||'事件关系';
}
