import type { ReportContextResource } from "../../api/client";
import { reportContextResourceFromRecord } from "../reports/reportContext";

export type AnnotationContextResource = {
  resource_id: string;
  source_record_id: string;
  annotation_text: string;
  preview?: string;
};

export type FileContextResource = {
  resource_id: string;
  original_filename: string;
  mime_type?: string;
};

export type UploadingResource = {
  progress_key: string;
  originalFilename: string;
  progress: number;
};

type ContextResourcePartition = {
  annotations: AnnotationContextResource[];
  files: FileContextResource[];
  reports: ReportContextResource[];
};

function annotationContextResourceFromRecord(
  resource: Record<string, unknown>,
  index: number,
  fallbackId: string
) {
  if (
    resource.resource_type !== "record_annotation" ||
    typeof resource.annotation_text !== "string"
  ) {
    return null;
  }
  const annotationText = resource.annotation_text.trim();
  const sourceRecordId = typeof resource.source_record_id === "string"
    ? resource.source_record_id.trim()
    : "";
  if (!annotationText || !sourceRecordId) {
    return null;
  }
  return {
    resource_id:
      typeof resource.resource_id === "string"
        ? resource.resource_id
        : `${fallbackId}-annotation-${index}`,
    source_record_id: sourceRecordId,
    annotation_text: annotationText
  };
}

function fileContextResourceFromRecord(
  resource: Record<string, unknown>,
  index: number,
  fallbackId: string
) {
  if (resource.resource_type !== "file") {
    return null;
  }
  return {
    resource_id:
      typeof resource.resource_id === "string"
        ? resource.resource_id
        : `${fallbackId}-file-${index}`,
    original_filename:
      typeof resource.original_filename === "string" && resource.original_filename.trim()
        ? resource.original_filename.trim()
        : "附件",
    ...(typeof resource.mime_type === "string" ? { mime_type: resource.mime_type } : {})
  };
}

export function partitionContextResources(
  contextResources: Array<Record<string, unknown>>,
  fallbackId: string
): ContextResourcePartition {
  const partition: ContextResourcePartition = {
    annotations: [],
    files: [],
    reports: []
  };
  const seenReportIds = new Set<string>();
  contextResources.forEach((resource, index) => {
    const annotation = annotationContextResourceFromRecord(resource, index, fallbackId);
    if (annotation) {
      partition.annotations.push(annotation);
      return;
    }
    const file = fileContextResourceFromRecord(resource, index, fallbackId);
    if (file) {
      partition.files.push(file);
      return;
    }
    const report = reportContextResourceFromRecord(resource);
    if (report && !seenReportIds.has(report.resource_id)) {
      seenReportIds.add(report.resource_id);
      partition.reports.push(report);
    }
  });
  return partition;
}
