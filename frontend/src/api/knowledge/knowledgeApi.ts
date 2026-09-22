import { request } from "../transport/request";

export type KnowledgeDocument = {
  document_id: string;
  original_filename: string;
  mime_type: string;
  size_bytes: number;
  sha256: string;
  segment_count: number;
  created_at: string;
  download_url: string;
};

export type KnowledgeMatch = KnowledgeDocument & {
  segment_index: number;
  page_number: number | null;
  excerpt: string;
  score: number;
};

export type KnowledgeReading = {
  document: KnowledgeDocument;
  segments: { segment_index: number; page_number: number | null; content: string }[];
  segment_start: number;
  segment_end: number;
  next_segment: number | null;
};

const path = "/knowledge/documents";

export function readKnowledgeCatalog(cursor: string | null = null, signal?: AbortSignal) {
  return request<{ documents: KnowledgeDocument[]; total: number; next_cursor: string | null }>(
    `${path}${cursor ? `?cursor=${encodeURIComponent(cursor)}` : ""}`, { signal }
  );
}

export function searchKnowledge(query: string, signal?: AbortSignal) {
  return request<{ results: KnowledgeMatch[]; matching_documents: number; has_more: boolean }>(
    `${path}/search?query=${encodeURIComponent(query)}&limit=30`, { signal }
  );
}

export function uploadKnowledge(file: File) {
  const body = new FormData();
  body.append("file", file);
  return request<{ document: KnowledgeDocument }>(path, { method: "POST", body });
}

export function readKnowledgeFile(documentId: string, segmentStart = 1, signal?: AbortSignal) {
  return request<KnowledgeReading>(`${path}/${encodeURIComponent(documentId)}?segment_start=${segmentStart}&segment_count=8`, { signal });
}

export function deleteKnowledgeFile(documentId: string) {
  return request<{ document_id: string; deleted: boolean }>(`${path}/${encodeURIComponent(documentId)}`, { method: "DELETE" });
}
