import { useEffect, useRef, useState } from "react";

import type { QueuedConversationInput } from "../../api/client";
import { DocumentFormatIcon, EditIcon, GripIcon, TrashIcon, TurnRightIcon } from "../../components/icons";

type QueuedInputPanelProps = {
  items: QueuedConversationInput[];
  resourceUrl: (resourceId: string) => string;
  onDelete: (inputId: string) => void | Promise<void>;
  onEdit: (inputId: string) => void | Promise<void>;
  onReorder: (inputIds: string[]) => void | Promise<void>;
  onRunNow: (inputId: string) => void | Promise<void>;
};

export function QueuedInputPanel({
  items,
  resourceUrl,
  onDelete,
  onEdit,
  onReorder,
  onRunNow
}: QueuedInputPanelProps) {
  const [orderedItems, setOrderedItems] = useState(items);
  const orderedItemsRef = useRef(items);
  const draggedInputIdRef = useRef<string | null>(null);

  useEffect(() => {
    orderedItemsRef.current = items;
    setOrderedItems(items);
  }, [items]);

  function previewMove(inputId: string, targetInputId: string) {
    const current = orderedItemsRef.current;
    const from = current.findIndex((item) => item.input_id === inputId);
    const to = current.findIndex((item) => item.input_id === targetInputId);
    if (from < 0 || to < 0 || from === to) {
      return;
    }
    const next = [...current];
    const [moved] = next.splice(from, 1);
    next.splice(to, 0, moved);
    orderedItemsRef.current = next;
    setOrderedItems(next);
  }

  function commitOrder() {
    const inputIds = orderedItemsRef.current.map((item) => item.input_id);
    draggedInputIdRef.current = null;
    if (inputIds.some((inputId, index) => inputId !== items[index]?.input_id)) {
      void onReorder(inputIds);
    }
  }

  function moveByKeyboard(inputId: string, offset: -1 | 1) {
    const current = orderedItemsRef.current;
    const index = current.findIndex((item) => item.input_id === inputId);
    const target = current[index + offset];
    if (!target) {
      return;
    }
    previewMove(inputId, target.input_id);
    commitOrder();
  }

  return (
    <section aria-label="等候队列" className="queued-input-panel">
      <div className="queued-input-list">
        {orderedItems.map((item, index) => {
          const firstAttachment = item.context_resources.find(
            (resource) => resource.resource_type === "file"
          );
          return (
            <article
              className="queued-input-item"
              data-row-surface
              data-queued-input-id={item.input_id}
              key={item.input_id}
              onDragEnter={() => {
                const dragged = draggedInputIdRef.current;
                if (dragged) {
                  previewMove(dragged, item.input_id);
                }
              }}
              onDragOver={(event) => event.preventDefault()}
            >
              <button
                aria-label={`移动第 ${index + 1} 项，使用上下方向键调整`}
                className="queued-input-drag-handle"
                data-interaction-owner="self"
                draggable
                onDragEnd={commitOrder}
                onDragStart={() => {
                  draggedInputIdRef.current = item.input_id;
                }}
                onKeyDown={(event) => {
                  if (event.key === "ArrowUp") {
                    event.preventDefault();
                    moveByKeyboard(item.input_id, -1);
                  }
                  if (event.key === "ArrowDown") {
                    event.preventDefault();
                    moveByKeyboard(item.input_id, 1);
                  }
                }}
                onPointerDown={(event) => {
                  if (event.pointerType === "touch") {
                    draggedInputIdRef.current = item.input_id;
                    event.currentTarget.setPointerCapture(event.pointerId);
                  }
                }}
                onPointerMove={(event) => {
                  if (!draggedInputIdRef.current || event.pointerType !== "touch") {
                    return;
                  }
                  const target = document
                    .elementFromPoint(event.clientX, event.clientY)
                    ?.closest<HTMLElement>("[data-queued-input-id]")
                    ?.dataset.queuedInputId;
                  if (target) {
                    previewMove(draggedInputIdRef.current, target);
                  }
                }}
                onPointerUp={(event) => {
                  if (event.pointerType === "touch") {
                    commitOrder();
                  }
                }}
                title="拖动排序；也可用上下方向键"
                type="button"
              >
                <GripIcon className="queued-input-icon" />
              </button>
              <div className="queued-input-copy">
                {firstAttachment ? (
                  <QueuedAttachmentThumbnail
                    key={String(firstAttachment.resource_id)}
                    originalFilename={String(firstAttachment.original_filename || "附件")}
                    src={String(firstAttachment.mime_type || "").startsWith("image/")
                      ? resourceUrl(String(firstAttachment.resource_id)) : undefined}
                  />
                ) : null}
                <p title={item.content || "仅附件输入"}>{item.content || "仅附件输入"}</p>
              </div>
              <div className="queued-input-actions">
                <button
                  aria-label="调整方向"
                  className="control control--compact control--ghost queued-input-action"
                  data-interaction-owner="self"
                  onClick={() => void onRunNow(item.input_id)}
                  title="调整方向：中断当前轮次并立即执行此项"
                  type="button"
                >
                  <TurnRightIcon className="queued-input-icon" />
                  <span>调整方向</span>
                </button>
                <button aria-label="编辑" className="control control--compact control--ghost queued-input-action" data-interaction-owner="self" onClick={() => void onEdit(item.input_id)} title="取回编辑" type="button">
                  <EditIcon className="queued-input-icon" />
                  <span>编辑</span>
                </button>
                <button aria-label="删除" className="control control--compact control--ghost control--danger queued-input-action removal-action-control" data-interaction-owner="self" onClick={() => void onDelete(item.input_id)} title="删除" type="button">
                  <TrashIcon className="queued-input-icon" />
                  <span>删除</span>
                </button>
              </div>
            </article>
          );
        })}
      </div>
    </section>
  );
}

function QueuedAttachmentThumbnail({ originalFilename, src }: { originalFilename: string; src?: string }) {
  const [failedSrc, setFailedSrc] = useState<string>();
  return (
    <span aria-label={`附件：${originalFilename}`} className="queued-input-thumbnail" role="img" title={originalFilename}>
      {src && src !== failedSrc ? (
        <img alt="" draggable={false} loading="lazy" onError={() => setFailedSrc(src)} src={src} />
      ) : <DocumentFormatIcon className="queued-input-icon" />}
    </span>
  );
}
