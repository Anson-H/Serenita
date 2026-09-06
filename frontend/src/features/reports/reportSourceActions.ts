import type * as React from "react";
import {
  type Dispatch,
  type SetStateAction
} from "react";
import {
  apiClient,
  type ReportSourceFile
} from "../../api/client";
import type { ReportSourcePreview } from "./reportSourcePreview";

type Dependencies = {
  sourceRequestSequence: React.RefObject<number>;
  sourceObjectUrlRef: React.RefObject<string | null>;
  setSourcePreview: Dispatch<SetStateAction<ReportSourcePreview | null>>;
  setSourcePreviewLoading: Dispatch<SetStateAction<boolean>>;
  selectedReportIdRef: React.RefObject<string | null>;
  memberId: string;
  setActionError: Dispatch<SetStateAction<string>>;
  isCurrentScope: () => boolean;
};

export function createReportSourceActions({
  sourceRequestSequence,
  sourceObjectUrlRef,
  setSourcePreview,
  setSourcePreviewLoading,
  selectedReportIdRef,
  memberId,
  setActionError,
  isCurrentScope
}: Dependencies) {
  function clearSourcePreview() {
    sourceRequestSequence.current += 1;
    if (sourceObjectUrlRef.current) URL.revokeObjectURL(sourceObjectUrlRef.current);
    sourceObjectUrlRef.current = null;
    setSourcePreview(null);
    setSourcePreviewLoading(false);
  }

  async function openSourceFile(file: ReportSourceFile) {
    const reportId = selectedReportIdRef.current;
    if (!memberId || !reportId) return;
    const requestSequence = ++sourceRequestSequence.current;
    setSourcePreviewLoading(true);
    setActionError("");
    try {
      const blob = await apiClient.fetchReportSourceBlob(memberId,
        reportId,
        file.resource_id
      );
      const mimeType = blob.type || file.mime_type || "application/octet-stream";
      const textContent = mimeType.startsWith("text/") ? await blob.text() : undefined;
      if (!isCurrentScope() || selectedReportIdRef.current !== reportId || requestSequence !== sourceRequestSequence.current) return;
      if (sourceObjectUrlRef.current) URL.revokeObjectURL(sourceObjectUrlRef.current);
      const objectUrl = URL.createObjectURL(blob);
      sourceObjectUrlRef.current = objectUrl;
      setSourcePreview({
        file,
        mimeType,
        objectUrl,
        textContent
      });
    } catch (error) {
      if (isCurrentScope() && requestSequence === sourceRequestSequence.current && selectedReportIdRef.current === reportId) {
        setActionError(error instanceof Error ? error.message : "原始文件加载失败。");
      }
    } finally {
      if (isCurrentScope() && requestSequence === sourceRequestSequence.current && selectedReportIdRef.current === reportId) setSourcePreviewLoading(false);
    }
  }
  return {
    clearSourcePreview,
    openSourceFile
  };
}
