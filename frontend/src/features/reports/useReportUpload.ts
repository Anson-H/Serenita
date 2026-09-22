import { useEffect, useRef } from "react";
import { useAttachmentTask } from "../conversations/useAttachmentTask";
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
  const pendingReportUpload = useRef<File[] | null>(null);
  const [uploadedReportNames, setUploadedReportNames] = useScopedState<string[]>([], isCurrentUploadScope);
  useEffect(() => { pendingReportUpload.current = null; setReportUploading(false); setUploadedReportNames([]); }, [route, memberId, currentSessionId]);
  const submitFiles = useAttachmentTask({
    scopeKey: `${accountId}:${route}:${memberId}:${currentSessionId}`,
    uploadFiles, submitMessage, onUploaded: setUploadedReportNames,
  });
  const reportImportPrompt = "导入医疗报告";
  async function startReportUpload(files: File[]) {
    if (!files.length || uploadBusy.current) {
      return;
    }
    const errors = validateReportFiles(files);
    if (!canEdit) errors.push("当前成员没有医疗报告编辑权限。");
    if (unavailableReason) errors.push(unavailableReason);
    for (const file of files) {
      const mime = file.type === "image/heif" ? "image/heic" : file.type;
      if (mime && !mimeTypes.includes(mime)) errors.push(`${file.name}：当前模型配置无法读取该格式。`);
    }
    if (errors.length) { setUploadErrors(errors); return; }
    setUploadErrors([]);
    uploadBusy.current = true;
    setReportUploading(true);
    pendingReportUpload.current = files;
    try {
      await submitFiles(files, memberId, reportImportPrompt);
      if (!isCurrentUploadScope()) return;
      pendingReportUpload.current = null;
      setUploadedReportNames([]);
    } catch (error) {
      if (isCurrentUploadScope()) setUploadErrors([error instanceof Error ? error.message : "医疗报告附件上传失败。"]);
    } finally {
      uploadBusy.current = false;
      setReportUploading(false);
    }
  }

  return { reportUploading, uploadedReportNames, startReportUpload,
    canRetryReportUpload: Boolean(pendingReportUpload.current),
    retryReportUpload: () => pendingReportUpload.current ? startReportUpload(pendingReportUpload.current) : Promise.resolve(),
    remainingReportFiles: pendingReportUpload.current?.slice(uploadedReportNames.length) ?? [] };
}
