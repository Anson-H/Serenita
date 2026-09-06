import type { ConversationToolRecord } from "../../api/client";
import { citationSource, decodeTabularJson, isRecord, type WebCitationSource } from "../../utils/markdownCitations";

function logicalToolOutput(record: ConversationToolRecord) {
  const decoded = decodeTabularJson(record.result);
  if (!isRecord(decoded)) {
    return null;
  }
  return isRecord(decoded.output) ? decoded.output : decoded;
}

/** Build the trusted citation registry from the assistant turn's persisted Tool Results. */
export function webCitationSourcesFromToolRecords(
  records: readonly ConversationToolRecord[],
  turnId: string
): WebCitationSource[] {
  const sources = new Map<string, WebCitationSource>();
  for (const record of records) {
    if (record.turn_id !== turnId || record.status !== "completed") {
      continue;
    }
    const output = logicalToolOutput(record);
    const candidates = record.name === "web_search"
      ? output?.results
      : record.name === "web_read"
        ? output?.pages
        : null;
    if (!Array.isArray(candidates)) {
      continue;
    }
    for (const candidate of candidates) {
      const source = citationSource(candidate);
      if (!source) {
        continue;
      }
      const existing = sources.get(source.citationId);
      sources.set(source.citationId, existing?.snippet ? existing : source);
    }
  }
  return [...sources.values()];
}

