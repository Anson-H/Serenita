import {
  type ReportSourceFile
} from "../../api/client";

export type ReportSourcePreview = {
  file: ReportSourceFile;
  mimeType: string;
  objectUrl: string;
  textContent?: string;
};
