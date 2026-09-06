import {
  type CSSProperties
} from "react";
import type {
  ConversationResourceState,
  ReportContextResource,
  UploadedResource
} from "../../api/client";
import { GroupedList } from "../../components/GroupedList";
import { HealthRecordIcon, PaperclipIcon, QuoteIcon, XIcon } from "../../components/icons";
import { reportReferenceStatus } from "../reports/reportContext";
import { ContextInputPreview, displayModelInputText } from "./ContextInputPreview";
import {
  type AnnotationContextResource,
  type FileContextResource,
  type UploadingResource
} from "./contextResources";

function AnnotationPreviewList({ items, onRemove }: {
  items: { resourceId: string; text: string }[];
  onRemove?: (resourceId: string) => void;
}) {
  return (
    <GroupedList as="ol" density="compact" className="annotation-preview-list" aria-label="注释内容">
      {items.map((item, index) => (
        <li className="compact-control-bar annotation-preview-item" key={item.resourceId}>
          <span className="annotation-preview-index" aria-hidden="true">{index + 1}.</span>
          <p className="annotation-preview-copy">{item.text}</p>
          {onRemove ? (
            <button
              aria-label={`删除第 ${index + 1} 条注释`}
              className="control control--inline-compact control--icon control--ghost control--danger removal-action-control annotation-preview-remove"
              data-interaction-owner="self"
              onClick={() => onRemove(item.resourceId)}
              type="button"
            >
              <XIcon />
            </button>
          ) : null}
        </li>
      ))}
    </GroupedList>
  );
}

type AnnotationContextChipProps = {
  annotations: AnnotationContextResource[];
  onRemove: (resourceId: string) => void;
  onRemoveAll: () => void;
};

export function AnnotationContextChip({
  annotations,
  onRemove,
  onRemoveAll
}: AnnotationContextChipProps) {
  return (
    <ContextInputPreview
      ariaLabel={`预览发送给模型的 ${annotations.length} 条注释`}
      className="annotation-context-chip"
      emptyMessage="没有可显示的注释内容。"
      icon={<QuoteIcon />}
      label={`${annotations.length} 条注释`}
      previewContent={(
        <AnnotationPreviewList
          items={annotations.map(annotation => ({ resourceId: annotation.resource_id, text: annotation.annotation_text.trim() }))}
          onRemove={onRemove}
        />
      )}
      previewInteractive
      trailing={(
        <button
          aria-label="移除全部注释"
          className="control control--inline-compact control--icon control--ghost control--danger removal-action-control annotation-context-remove"
          data-interaction-owner="self"
          onClick={onRemoveAll}
          type="button"
        >
          <XIcon />
        </button>
      )}
    />
  );
}

type UploadedResourceChipProps = {
  href?: string;
  resource: UploadedResource;
  onRemove: (resourceId: string) => void;
};

export function UploadedResourceChip({ href, resource, onRemove }: UploadedResourceChipProps) {
  const content = <><PaperclipIcon /><span className="file-context-name">{resource.original_filename}</span></>;
  return (
    <span
      className="compact-control-bar file-context-chip"
      data-row-surface
      title={resource.original_filename}
    >
      {href ? (
        <a
          className="control control--inline-compact control--ghost"
          data-interaction-owner="row"
          aria-label={`打开附件：${resource.original_filename}`}
          href={href}
          rel="noreferrer"
          target="_blank"
        >
          {content}
        </a>
      ) : (
        <button
          className="control control--inline-compact control--ghost"
          data-interaction-owner="row"
          aria-label={`附件正在准备：${resource.original_filename}`}
          disabled
          type="button"
        >
          {content}
        </button>
      )}
      {onRemove ? (
        <button
          className="control control--inline-compact control--icon control--ghost control--danger removal-action-control"
          data-interaction-owner="self"
          aria-label={`移除附件：${resource.original_filename}`}
          onClick={() => onRemove(resource.resource_id)}
          type="button"
        >
          <XIcon />
        </button>
      ) : undefined}
    </span>
  );
}

type UploadingResourceChipProps = {
  resource: UploadingResource;
};

export function UploadingResourceChip({ resource }: UploadingResourceChipProps) {
  return (
    <span
      aria-label={`正在上传：${resource.originalFilename}`}
      className="compact-control-bar file-context-chip file-context-chip-uploading"
      tabIndex={0}
      title={resource.originalFilename}
    >
      <span
        aria-label={`上传进度 ${resource.progress}%`}
        aria-valuemax={100}
        aria-valuemin={0}
        aria-valuenow={resource.progress}
        className="file-upload-progress"
        role="progressbar"
        style={{ "--upload-progress": `${resource.progress}%` } as CSSProperties}
      />
      <span className="file-context-name">{resource.originalFilename}</span>
    </span>
  );
}

type MessageAnnotationReferencesProps = {
  annotations: AnnotationContextResource[];
  modelInputTextByResourceId?: Record<string, string>;
  onRemove?: (resourceId: string) => void;
};

export function MessageAnnotationReferences({
  annotations,
  modelInputTextByResourceId = {},
  onRemove
}: MessageAnnotationReferencesProps) {
  return (
    <ContextInputPreview
      ariaLabel={`预览发送给模型的 ${annotations.length} 条注释`}
      className="message-file-reference message-annotation-reference"
      align="end"
      emptyMessage="这条历史消息没有记录注释输入。"
      icon={<QuoteIcon />}
      label={`${annotations.length} 条注释`}
      previewContent={(
        <AnnotationPreviewList
          items={annotations.map(annotation => {
            const modelInputText = modelInputTextByResourceId[annotation.resource_id];
            return {
              resourceId: annotation.resource_id,
              text: modelInputText
                ? displayModelInputText(modelInputText)
                : "这条历史请求没有记录对应的模型输入。"
            };
          })}
          onRemove={onRemove}
        />
      )}
      previewInteractive={Boolean(onRemove)}
    />
  );
}

type MessageFileReferenceProps = {
  href?: string;
  resource: FileContextResource;
  onRemove?: (resourceId: string) => void;
};

export function MessageFileReference({ href, resource, onRemove }: MessageFileReferenceProps) {
  const content = <><PaperclipIcon /><span className="message-file-copy">{resource.original_filename}</span></>;
  return (
    <span
      className="compact-control-bar message-file-reference"
      data-row-surface
      title={resource.mime_type ? `${resource.original_filename} · ${resource.mime_type}` : resource.original_filename}
    >
      {href ? (
        <a
          className="control control--inline-compact control--ghost"
          data-interaction-owner="row"
          aria-label={`打开附件：${resource.original_filename}`}
          href={href}
          rel="noreferrer"
          target="_blank"
        >
          {content}
        </a>
      ) : (
        <button
          className="control control--inline-compact control--ghost"
          data-interaction-owner="row"
          aria-label={`附件暂时无法打开：${resource.original_filename}`}
          disabled
          type="button"
        >
          {content}
        </button>
      )}
      {onRemove ? (
        <button
          className="control control--inline-compact control--icon control--ghost control--danger removal-action-control"
          data-interaction-owner="self"
          aria-label={`移除附件：${resource.original_filename}`}
          onClick={() => onRemove(resource.resource_id)}
          type="button"
        >
          <XIcon />
        </button>
      ) : undefined}
    </span>
  );
}

type MessageReportReferenceProps = {
  modelInputText?: string;
  onOpen: (reportId: string) => void | Promise<void>;
  resource: ReportContextResource;
  resourceState?: ConversationResourceState;
  onRemove?: (resourceId: string) => void;
};

export function MessageReportReference({
  modelInputText,
  onOpen,
  resource,
  resourceState,
  onRemove
}: MessageReportReferenceProps) {
  const name = resource.report_name;
  const currentStatus = reportReferenceStatus(resource, resourceState);
  return (
    <ContextInputPreview
      ariaLabel={`预览报告输入：${name}`}
      className="message-file-reference message-report-reference"
      align="end"
      emptyMessage="没有可显示的报告输入快照。"
      icon={<HealthRecordIcon />}
      label={`报告输入 · ${name}`}
      previewContent={(
        <div className="message-report-input-preview">
          {modelInputText ? (
            <pre>{displayModelInputText(modelInputText)}</pre>
          ) : (
            <span className="context-input-status">没有可显示的报告输入快照。</span>
          )}
          <div className="message-report-current-resource">
            {currentStatus === "unknown" ? <span className="message-report-current-status">状态待刷新</span> : null}
            {currentStatus === "modified" ? (
              <span className="message-report-current-status">当前报告已修改</span>
            ) : null}
            {currentStatus === "deleted" || currentStatus === "forbidden" ? (
              <span className="message-report-current-status">{currentStatus === "forbidden" ? "无权访问" : "当前报告已删除"}</span>
            ) : (
              <button
                className="message-report-open-current"
                onClick={() => void onOpen(resource.resource_id)}
                type="button"
              >
                打开当前报告
              </button>
            )}
          </div>
        </div>
      )}
      previewInteractive
      trailing={onRemove ? (
        <button
          aria-label={`移除报告输入：${name}`}
          className="control control--inline-compact control--icon control--ghost control--danger removal-action-control file-context-remove message-file-remove"
          data-interaction-owner="self"
          onClick={() => onRemove(resource.resource_id)}
          type="button"
        >
          <XIcon />
        </button>
      ) : undefined}
    />
  );
}
