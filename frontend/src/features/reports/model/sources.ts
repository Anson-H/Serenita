/** 管理医疗报告来源预览的读取状态、迟到结果和对象 URL 生命周期。 */
import type { ReportSourceFile } from "../../../api/client";
import type { ReportDetailState } from "./detail";
import { ReportStore } from "./store";

export type ReportSourcePreview = {
  file: ReportSourceFile;
  mimeType: string;
  objectUrl: string;
  textContent?: string;
};

export class ReportSourceActions extends ReportStore<{
  sourcePreview: ReportSourcePreview | null;
  sourcePreviewLoading: boolean;
}> {
  private request = 0;
  constructor(private detail: ReportDetailState, private options: {
    read: (memberId: string, reportId: string, resourceId: string) => Promise<Blob>;
    onError: (message: string) => void;
  }) {
    super({ sourcePreview: null, sourcePreviewLoading: false });
    detail.onSelectionInvalidated(this.clearSourcePreview);
  }

  clearSourcePreview = () => {
    this.request++;
    if (this.state.sourcePreview) URL.revokeObjectURL(this.state.sourcePreview.objectUrl);
    this.publish({ sourcePreview: null, sourcePreviewLoading: false });
  };

  openSourceFile = async (file: ReportSourceFile) => {
    const operation = this.detail.capture();
    if (!operation.reportId || !operation.isCurrent()) return;
    const request = ++this.request;
    const isCurrent = () => operation.isCurrent() && request === this.request;
    this.publish({ sourcePreviewLoading: true });
    this.options.onError("");
    try {
      const blob = await this.options.read(this.detail.memberId, operation.reportId, file.resource_id);
      const mimeType = blob.type || file.mime_type || "application/octet-stream";
      const textContent = mimeType.startsWith("text/") ? await blob.text() : undefined;
      if (!isCurrent()) return;
      if (this.state.sourcePreview) URL.revokeObjectURL(this.state.sourcePreview.objectUrl);
      this.publish({ sourcePreview: { file, mimeType, objectUrl: URL.createObjectURL(blob), textContent } });
    } catch (error) {
      if (isCurrent()) this.options.onError(error instanceof Error ? error.message : "原始文件加载失败。");
    } finally {
      if (isCurrent()) this.publish({ sourcePreviewLoading: false });
    }
  };
}
