import { ModelIdentity } from "./ModelIdentity";
import {
  memo,
  useMemo
} from "react";
import type {
  ConversationContextRecord,
  ConversationErrorRecord,
  ConversationModelRecord,
  ConversationObservationRecord,
  ConversationToolRecord
} from "../../api/client";
import {
  AlertIcon,
  ExecutionStageIcon,
  type ExecutionStage
} from "../../components/icons";
import { MarkdownContent } from "../../components/MarkdownContent";
import {
  compactionModelRecords,
  compactionStatusLabel,
  compactionTokenLabel
} from "./contextCompactionDisplay";

import {
  type ConversationExecutionRecord
} from "./conversationTurns";
import { ModelRecordDurationLabel } from "./ExecutionDuration";
import { conversationTurnFailureMessage, firstVisibleLine, FormattedRecordValue, LiveDisclosurePreview, previewRecordValue, providerSourceLabel, TraceChevron, TraceItemSeparator } from "./ExecutionRecordPrimitives";
import { formatThinkingDuration } from "./thinking";
import { useDeferredDisclosureBody } from "./useExecutionDisclosure";

const MODEL_CHANNEL_LABELS: Record<
  Exclude<ConversationModelRecord["channel"], "input" | "result" | "content">,
  string
> = {
  reasoning: "思考过程",
  raw_output: "模型原始文本",
  tool_request: "请求工具调用"
};

export const ContextRecordDetails = memo(function ContextRecordDetails({
  highlighted,
  onRegister,
  record
}: {
  highlighted: boolean;
  onRegister: (recordId: string, node: HTMLElement | null) => void;
  record: ConversationContextRecord;
}) {
  const { bodyMounted, onToggle } = useDeferredDisclosureBody();
  const sourceLabel = providerSourceLabel(record);

  return (
    <details
      className="turn-trace-item operation-record context-record"
      data-row-surface
      data-current={highlighted ? "true" : undefined}
      data-highlighted={highlighted ? "true" : undefined}
      onToggle={onToggle}
      ref={(node) => onRegister(record.record_id, node)}
    >
      <summary className="compact-control-bar" data-interaction-owner="self" data-row-trigger>
        <span className="turn-trace-item-icon">
          <ExecutionStageIcon stage="context" />
        </span>
        <span className="turn-trace-item-copy">
          <span className="turn-trace-item-label">上下文注入</span>
          <TraceItemSeparator />
          <span className="turn-trace-item-preview">{record.label}</span>
          <TraceChevron />
        </span>
      </summary>
      {bodyMounted ? <div className="operation-record-body">
        {sourceLabel ? (
          <p className="context-record-source">
            <span>模型输入来源</span>
            <code>{sourceLabel}</code>
          </p>
        ) : null}
        <FormattedRecordValue value={record.content} />
      </div> : null}
    </details>
  );
});

export const CompactionStatusRecord = memo(function CompactionStatusRecord({
  highlighted,
  onRegister,
  record,
  records
}: {
  highlighted: boolean;
  onRegister: (recordId: string, node: HTMLElement | null) => void;
  record: ConversationContextRecord;
  records: ConversationExecutionRecord[];
}) {
  const { bodyMounted, onToggle } = useDeferredDisclosureBody();
  const modelRecords = useMemo(() => compactionModelRecords(record, records), [record, records]);
  const tokenLabel = compactionTokenLabel(record);
  return (
    <details
      className="turn-trace-item operation-record context-record"
      data-row-surface
      data-highlighted={highlighted ? "true" : undefined}
      onToggle={onToggle}
      ref={(node) => onRegister(record.record_id, node)}
    >
      <summary className="compact-control-bar" data-interaction-owner="self" data-row-trigger>
        <span className="turn-trace-item-icon"><ExecutionStageIcon stage="context" /></span>
        <span className="turn-trace-item-copy">
          <span className="turn-trace-item-label">上下文压缩</span>
          <TraceItemSeparator />
          <span className="turn-trace-item-label" role="status">{compactionStatusLabel(record)}</span>
          <TraceItemSeparator />
          <span className="turn-trace-item-preview" title={tokenLabel}>{tokenLabel}</span>
          <TraceChevron />
        </span>
      </summary>
      {bodyMounted ? <div className="operation-record-body">
        <p>{tokenLabel}</p>
        {record.error ? <section className="operation-record-error">
          <FormattedRecordValue value={record.error} />
        </section> : null}
        {modelRecords.length ? <section>
          <h4>压缩模型记录</h4>
          <FormattedRecordValue value={modelRecords.map((model) => ({
            call_id: model.call_id,
            summary_kind: model.summary_kind,
            label: model.summary_kind === "history" ? "历史摘要"
              : model.summary_kind === "turn_prefix" ? "轮次前半段摘要" : "压缩摘要",
            channel: model.channel,
            model_id: model.model_id,
            status: model.status,
            value: model.value,
            usage: model.usage,
            error: model.error
          }))} />
        </section> : null}
      </div> : null}
    </details>
  );
});

export const ModelRecordDetails = memo(function ModelRecordDetails({
  highlighted,
  onRegister,
  showModelIdentity,
  record
}: {
  highlighted: boolean;
  onRegister: (recordId: string, node: HTMLElement | null) => void;
  record: ConversationModelRecord;
  showModelIdentity: boolean;
}) {
  const { bodyMounted, onToggle } = useDeferredDisclosureBody();
  if (
    record.channel === "input" ||
    record.channel === "result" ||
    record.channel === "content"
  ) {
    return null;
  }
  const streaming = record.status === "streaming" || record.status === "running";
  const label = MODEL_CHANNEL_LABELS[record.channel];
  const textValue = typeof record.value === "string" ? record.value : "";
  const previewText = record.channel === "tool_request"
    ? record.name || "等待工具请求"
    : previewRecordValue(record.value);
  const stage: ExecutionStage = record.channel === "reasoning"
    ? "reasoning"
    : record.channel === "tool_request"
      ? "tool"
      : "content";
  return (
    <details
      className={`turn-trace-item operation-record model-record model-${record.channel}-record`}
      data-row-surface
      data-current={highlighted ? "true" : undefined}
      data-highlighted={highlighted ? "true" : undefined}
      onToggle={onToggle}
      ref={(node) => onRegister(record.record_id, node)}
    >
      <summary className="compact-control-bar" data-interaction-owner="self" data-row-trigger>
        <span className="turn-trace-item-icon"><ExecutionStageIcon stage={stage} /></span>
        <span className="turn-trace-item-copy">
          <span className="turn-trace-item-label">{label}</span>
          <LiveDisclosurePreview
            fallback={label}
            followLatest={record.channel === "reasoning"}
            streaming={streaming}
            text={previewText}
          />
          <TraceItemSeparator />
          <ModelRecordDurationLabel record={record} />
          <TraceChevron />
        </span>
      </summary>
      {bodyMounted ? <div className="operation-record-body">
        {showModelIdentity ? <ModelIdentity modelId={record.model_id} /> : null}
        {record.channel === "reasoning"
          ? (textValue ? <MarkdownContent className="scroll-balanced" content={textValue} /> : null)
          : <pre className="scroll-balanced">{typeof record.value === "string"
            ? record.value
            : JSON.stringify(record.value) ?? ""}</pre>}
        {record.error ? (
          <section className="operation-record-error">
            <h4>错误</h4>
            <FormattedRecordValue value={record.error} />
          </section>
        ) : null}
      </div> : null}
    </details>
  );
});

export const ModelContentRecord = memo(function ModelContentRecord({
  highlighted,
  onRegister,
  showModelIdentity,
  record
}: {
  highlighted: boolean;
  onRegister: (recordId: string, node: HTMLElement | null) => void;
  record: ConversationModelRecord;
  showModelIdentity: boolean;
}) {
  const textValue = typeof record.value === "string" ? record.value : "";
  if (!textValue && !record.error) {
    return null;
  }
  return (
    <article
      className="message-entry assistant execution-assistant-response"
      data-highlighted={highlighted ? "true" : undefined}
      ref={(node) => onRegister(record.record_id, node)}
    >
      {showModelIdentity ? <ModelIdentity modelId={record.model_id} /> : null}
      {textValue ? (
        <div className="message-bubble assistant">
          <MarkdownContent
            annotationSourceId={record.record_id}
            content={textValue}
            processCitations={false}
          />
        </div>
      ) : null}
      {record.error ? (
        <section className="operation-record-error execution-assistant-response-error">
          <FormattedRecordValue value={record.error} />
        </section>
      ) : null}
    </article>
  );
});

export const TurnErrorRecord = memo(function TurnErrorRecord({
  highlighted,
  onRegister,
  record
}: {
  highlighted: boolean;
  onRegister: (recordId: string, node: HTMLElement | null) => void;
  record: ConversationErrorRecord;
}) {
  const { bodyMounted, onToggle } = useDeferredDisclosureBody();
  const failureMessage = conversationTurnFailureMessage(record.error);
  return (
    <details
      className="turn-trace-item operation-record conversation-turn-error"
      data-current={highlighted ? "true" : undefined}
      data-highlighted={highlighted ? "true" : undefined}
      data-row-surface
      onToggle={onToggle}
      ref={(node) => onRegister(record.record_id, node)}
    >
      <summary className="compact-control-bar" data-interaction-owner="self" data-row-trigger>
        <span className="turn-trace-item-icon"><AlertIcon className="execution-record-icon" /></span>
        <span className="turn-trace-item-copy">
          <span className="turn-trace-item-label" role="alert">本轮执行失败</span>
          <TraceItemSeparator />
          <span className="turn-trace-item-preview">
            {firstVisibleLine(failureMessage) || "查看错误详情"}
          </span>
          <TraceChevron />
        </span>
      </summary>
      {bodyMounted ? <div className="operation-record-body">
        <pre className="scroll-balanced">{failureMessage}</pre>
      </div> : null}
    </details>
  );
});

export const ObservationRecord = memo(function ObservationRecord({
  highlighted,
  onRegister,
  record
}: {
  highlighted: boolean;
  onRegister: (recordId: string, node: HTMLElement | null) => void;
  record: ConversationObservationRecord;
}) {
  const { bodyMounted, onToggle } = useDeferredDisclosureBody();
  const failed = record.status === "failed";
  return (
    <details
      className="turn-trace-item operation-record observation"
      data-row-surface
      data-current={highlighted ? "true" : undefined}
      data-highlighted={highlighted ? "true" : undefined}
      onToggle={onToggle}
      ref={(node) => onRegister(record.record_id, node)}
    >
      <summary className="compact-control-bar" data-interaction-owner="self" data-row-trigger>
        <span className="turn-trace-item-icon"><ExecutionStageIcon stage="observation" /></span>
        <span className="turn-trace-item-copy">
          <span className="turn-trace-item-label">Harness 观测</span>
          <TraceItemSeparator />
          <span className="turn-trace-item-preview">
            {firstVisibleLine(previewRecordValue(record.observation)) || "模型已接收执行结果"}
          </span>
          <TraceItemSeparator />
          <span className="turn-trace-item-meta">{failed ? "失败" : "已记录"}</span>
          <TraceChevron />
        </span>
      </summary>
      {bodyMounted ? <div className="operation-record-body">
        <FormattedRecordValue value={record.observation} />
      </div> : null}
    </details>
  );
});

export const OperationRecord = memo(function OperationRecord({
  highlighted,
  modelReadableContent,
  onRegister,
  record
}: {
  highlighted: boolean;
  modelReadableContent: unknown;
  onRegister: (recordId: string, node: HTMLElement | null) => void;
  record: ConversationToolRecord;
}) {
  const { bodyMounted, onToggle } = useDeferredDisclosureBody();
  const statusLabel = record.status === "running"
    ? "执行中"
    : record.status === "completed"
      ? "已完成"
      : record.status === "interrupted"
        ? "已中断"
        : "执行失败";

  return (
    <details
      className={`turn-trace-item operation-record ${record.kind}`}
      data-row-surface
      data-current={highlighted ? "true" : undefined}
      data-highlighted={highlighted ? "true" : undefined}
      onToggle={onToggle}
      ref={(node) => onRegister(record.record_id, node)}
    >
      <summary className="compact-control-bar" data-interaction-owner="self" data-row-trigger>
        <span className="turn-trace-item-icon">
          <ExecutionStageIcon stage="tool" />
        </span>
        <span className="turn-trace-item-copy">
          <span className="turn-trace-item-label">工具调用结果</span>
          <TraceItemSeparator />
          <span className="turn-trace-item-preview">
            {record.name || "未知工具"}
          </span>
          <TraceItemSeparator />
          <span className="turn-trace-item-meta">
            {statusLabel}{record.duration_ms ? ` · ${formatThinkingDuration(record.duration_ms)}` : ""}
          </span>
          <TraceChevron />
        </span>
      </summary>
      {bodyMounted ? <div className="operation-record-body">
        {record.error ? (
          <section className="operation-record-error">
            <FormattedRecordValue value={modelReadableContent} />
          </section>
        ) : (
          <FormattedRecordValue value={modelReadableContent} />
        )}
      </div> : null}
    </details>
  );
});
