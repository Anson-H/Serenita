import { useRef } from "react";
import type { useConversationAttachments } from "./useConversationAttachments";
import type { useConversationWorkspace } from "./useConversationWorkspace";

type AttachmentTask = {
  scope: object;
  files: File[];
  sessionId: string | null;
  uploaded: Array<{
    resource_type: string;
    resource_id: string;
    original_filename: string;
  }>;
};

/** Keep successfully uploaded files available when upload or submission needs a retry. */
export function useAttachmentTask({
  scopeKey,
  uploadFiles,
  submitMessage,
  onUploaded,
}: {
  scopeKey: string;
  uploadFiles: ReturnType<typeof useConversationAttachments>["uploadFiles"];
  submitMessage: ReturnType<
    typeof useConversationWorkspace
  >["submitConversationMessage"];
  onUploaded?: (names: string[]) => void;
}) {
  const scope = useRef({ key: scopeKey });
  if (scope.current.key !== scopeKey) scope.current = { key: scopeKey };
  const pending = useRef<AttachmentTask | null>(null);

  return async (files: File[], memberId: string, rawText: string) => {
    const captured = scope.current;
    const isCurrent = () => scope.current === captured;
    let task = pending.current;
    if (
      !task ||
      task.scope !== captured ||
      task.files.length !== files.length ||
      task.files.some((file, index) => file !== files[index])
    ) {
      task = { scope: captured, files, sessionId: null, uploaded: [] };
      pending.current = task;
    }
    const remaining = files.slice(task.uploaded.length);
    onUploaded?.(task.uploaded.map(resource => resource.original_filename));
    if (remaining.length)
      await uploadFiles(remaining, task.sessionId, {
        memberId,
        isCurrent,
        onUploaded: (sessionId, resource) => {
          task.sessionId = sessionId;
          task.uploaded.push({
            resource_type: "file",
            resource_id: resource.resource_id,
            original_filename: resource.original_filename,
          });
          onUploaded?.(task.uploaded.map(item => item.original_filename));
        },
      });
    if (!isCurrent()) return;
    const sent = await submitMessage({
      isCurrent,
      rawText,
      contextResources: task.uploaded,
      sessionId: task.sessionId,
      memberId,
      startNewConversation: true,
    });
    if (!sent) throw new Error("识别任务未发送，已上传文件保留，请重试。");
    if (pending.current === task) pending.current = null;
  };
}
