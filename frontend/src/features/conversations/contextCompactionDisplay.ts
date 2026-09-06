import type { ConversationContextRecord, ConversationModelRecord } from "../../api/client";
import type { ConversationExecutionRecord } from "./conversationTurns";

export function isCompactionStatus(record: ConversationContextRecord) {
  return record.context_type === "compaction_status" && record.purpose === "context_compaction";
}

// A status record precedes its calls and keeps its position when the operation ends.
export function compactionModelRecords(
  status: ConversationContextRecord,
  records: readonly ConversationExecutionRecord[]
) {
  const start = records.findIndex((record) => record.record_id === status.record_id);
  if (start < 0) return [];
  const calls: ConversationModelRecord[] = [];
  for (const record of records.slice(start + 1)) {
    if (record.kind === "context" && isCompactionStatus(record)) break;
    if (record.kind === "model" && record.purpose === "context_compaction" &&
      record.turn_id === status.turn_id && record.channel !== "input") calls.push(record);
  }
  return calls;
}

export function compactionStatusLabel(record: ConversationContextRecord) {
  if (record.error || record.status === "failed") return "压缩失败";
  if (record.status === "running") return "运行中";
  if (record.status === "completed") return "已完成";
  return record.status;
}

export function compactionTokenLabel(record: ConversationContextRecord) {
  const format = (value: number | undefined) => typeof value === "number" &&
    Number.isSafeInteger(value) && value >= 0 ? value.toLocaleString("zh-CN") : "—";
  return `估算词元 ${format(record.estimated_tokens_before)} → ${format(record.estimated_tokens_after)}，目标 ${format(record.target_tokens)}`;
}
