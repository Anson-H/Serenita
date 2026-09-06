import { useEffect, useRef } from "react";
import type { UploadedResource } from "../../api/client";
import { useActiveScope } from "../../utils/useActiveScope";
import { useScopedState } from "../../utils/useScopedState";
import type { useConversationAttachments } from "../conversations/useConversationAttachments";
import type { useConversationWorkspace } from "../conversations/useConversationWorkspace";
import { validateReportFiles } from "./reportUploadValidation";

type ReportUploadOptions = {
  accountId: string;
  route: string;
  memberId: string;
  currentSessionId: string | null;
  canEdit: boolean;
  unavailableReason: string;
  mimeTypes: string[];
  setUploadErrors: (errors: string[]) => void;
  uploadFiles: ReturnType<typeof useConversationAttachments>["uploadFiles"];
  submitMessage: ReturnType<typeof useConversationWorkspace>["submitConversationMessage"];
};

export function useReportUpload({ accountId, route, memberId, currentSessionId, canEdit, unavailableReason, mimeTypes, setUploadErrors, uploadFiles, submitMessage }: ReportUploadOptions) {
  const isCurrentUploadScope = useActiveScope(`${accountId}:${route}:${memberId}:${currentSessionId}`);
  const [reportUploading, setReportUploading] = useScopedState(false, isCurrentUploadScope);
  const uploadBusy = useRef(false);
  const pendingReportUpload = useRef<{ scope: string; sessionId: string | null; resources: UploadedResource[]; remaining: File[] } | null>(null);
  const [uploadedReportNames, setUploadedReportNames] = useScopedState<string[]>([], isCurrentUploadScope);
  useEffect(() => { setReportUploading(false); setUploadedReportNames([]); }, [route, memberId, currentSessionId]);
  const reportImportPrompt = "导入医疗报告";
  async function startReportUpload(files: File[]) {
    if (!files.length || uploadBusy.current) {
      return;
    }
    const errors = validateReportFiles(files);
    if (!canEdit) errors.push("当前成员没有报告编辑权限。");
    if (unavailableReason) errors.push(unavailableReason);
    for (const file of files) {
      const mime = file.type === "image/heif" ? "image/heic" : file.type;
      if (mime && !mimeTypes.includes(mime)) errors.push(`${file.name}：当前模型配置无法读取该格式。`);
    }
    if (errors.length) { setUploadErrors(errors); return; }
    setUploadErrors([]);
    uploadBusy.current = true;
    setReportUploading(true);
    const scope = `${accountId}:${memberId}`;
    const pending = pendingReportUpload.current?.scope === scope && pendingReportUpload.current.remaining === files
      ? pendingReportUpload.current : { scope, sessionId: null, resources: [], remaining: files };
    pendingReportUpload.current = pending;
    setUploadedReportNames(pending.resources.map(resource => resource.original_filename));
    try {
      await uploadFiles(files, pending.sessionId, {
        memberId: memberId,
        isCurrent: isCurrentUploadScope,
        onUploaded: (sessionId, resource) => {
          pending.sessionId = sessionId;
          pending.resources.push(resource);
          pending.remaining = pending.remaining.slice(1);
          setUploadedReportNames(pending.resources.map(item => item.original_filename));
        }
      });
      if (!isCurrentUploadScope()) return;
      const upload = pending;
      setReportUploading(false);
      await submitMessage({
        rawText: reportImportPrompt,
        contextResources: upload.resources.map((resource) => ({
          resource_type: "file",
          resource_id: resource.resource_id,
          original_filename: resource.original_filename
        })),
        sessionId: upload.sessionId,
        memberId: memberId,
        isCurrent: isCurrentUploadScope,
        startNewConversation: true,
        onSubmitted: () => { pendingReportUpload.current = null; setUploadedReportNames([]); }
      });
    } catch (error) {
      if (isCurrentUploadScope()) setUploadErrors([error instanceof Error ? error.message : "报告附件上传失败。"]);
    } finally {
      uploadBusy.current = false;
      setReportUploading(false);
    }
  }

  return { reportUploading, uploadedReportNames, startReportUpload, remainingReportFiles: pendingReportUpload.current?.remaining ?? [] };
}
