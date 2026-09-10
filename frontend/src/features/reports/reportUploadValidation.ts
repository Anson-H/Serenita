const MAX_REPORT_FILES = 20;
const MAX_REPORT_FILE_BYTES = 20 * 1024 * 1024;
const MAX_REPORT_BATCH_BYTES = 100 * 1024 * 1024;
export const REPORT_FILE_ACCEPT = ".pdf,.jpg,.jpeg,.png,.heic,image/jpeg,image/png,image/heic,application/pdf";

const allowedMimeTypes = new Set([
  "application/pdf",
  "image/jpeg",
  "image/png",
  "image/heic",
  "image/heif"
]);
const allowedExtensions = new Set(["pdf", "jpg", "jpeg", "png", "heic"]);

type ReportFileLike = {
  name: string;
  size: number;
  type: string;
};

export function validateReportFiles(files: ReportFileLike[]) {
  const errors: string[] = [];
  if (!files.length) {
    errors.push("请先选择要上传的医疗报告文件。");
    return errors;
  }
  if (files.length > MAX_REPORT_FILES) {
    errors.push(`每批最多上传 ${MAX_REPORT_FILES} 个文件。`);
  }
  if (files.reduce((total, file) => total + file.size, 0) > MAX_REPORT_BATCH_BYTES) {
    errors.push("单批医疗报告文件总大小不能超过 100MB。");
  }

  files.forEach((file) => {
    const extension = file.name.split(".").pop()?.toLowerCase() ?? "";
    const mimeType = file.type.toLowerCase();
    if (
      !allowedExtensions.has(extension) ||
      (mimeType !== "" && !allowedMimeTypes.has(mimeType))
    ) {
      errors.push(`${file.name}：仅支持 PDF、JPG、PNG 或 HEIC。`);
    }
    if (file.size > MAX_REPORT_FILE_BYTES) {
      errors.push(`${file.name}：文件超过 20MB。`);
    }
    if (file.size <= 0) {
      errors.push(`${file.name}：文件内容为空。`);
    }
  });

  return errors;
}
