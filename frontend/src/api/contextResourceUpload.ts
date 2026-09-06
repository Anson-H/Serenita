import type { UploadedResource } from "./types";

export type ContextResourceUploadResponse = {
  session_id: string;
  member_id?: string | null;
  resource: UploadedResource;
};

function isNonEmptyString(value: unknown): value is string {
  return typeof value === "string" && Boolean(value.trim());
}

export function parseContextResourceUploadResponse(
  value: unknown
): ContextResourceUploadResponse {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new Error("上传响应无效。");
  }
  const response = value as Record<string, unknown>;
  const resourceValue = response.resource;
  if (
    !isNonEmptyString(response.session_id) ||
    !resourceValue ||
    typeof resourceValue !== "object" ||
    Array.isArray(resourceValue)
  ) {
    throw new Error("上传响应无效。");
  }
  const resource = resourceValue as Record<string, unknown>;
  if (
    !isNonEmptyString(resource.resource_id) ||
    !isNonEmptyString(resource.original_filename) ||
    !isNonEmptyString(resource.mime_type) ||
    typeof resource.size_bytes !== "number" ||
    !Number.isInteger(resource.size_bytes) ||
    resource.size_bytes < 0 ||
    !isNonEmptyString(resource.relative_path) ||
    !isNonEmptyString(resource.sha256) ||
    resource.storage_status !== "ready" ||
    resource.lifecycle_status !== "pending" ||
    !isNonEmptyString(resource.expires_at)
  ) {
    throw new Error("上传响应无效。");
  }
  return value as ContextResourceUploadResponse;
}
