export type WebCitationSource = {
  citationId: string;
  title: string;
  url: string;
  domain: string;
  snippet: string;
  publishedAt?: string | null;
};

type DisplayCitation = WebCitationSource & {
  number: number;
};

const CITATION_MARKER = /\[cite:([\w-]+)\]/g;
const MARKDOWN_CODE = /```[\s\S]*?```|`[^`\n]*`/g;
export const CITATION_HREF_PREFIX = "#serenita-citation-";

export function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

/** Restore the lossless $keys/$rows Tool Observation encoding for UI consumers. */
export function decodeTabularJson(value: unknown): unknown {
  if (Array.isArray(value)) {
    return value.map(decodeTabularJson);
  }
  if (!isRecord(value)) {
    return value;
  }
  const keysValue = value.$keys;
  const rowsValue = value.$rows;
  if (
    Object.keys(value).length === 2
    && Array.isArray(keysValue)
    && keysValue.every((key) => typeof key === "string")
    && Array.isArray(rowsValue)
    && rowsValue.every((row) => Array.isArray(row) && row.length === keysValue.length)
  ) {
    const keys = keysValue as string[];
    return rowsValue.map((row) =>
      Object.fromEntries(keys.map((key, index) => [key, decodeTabularJson(row[index])]))
    );
  }
  return Object.fromEntries(
    Object.entries(value).map(([key, item]) => [key, decodeTabularJson(item)])
  );
}

function mapMarkdownOutsideCode(content: string, transform: (text: string) => string) {
  MARKDOWN_CODE.lastIndex = 0;
  let cursor = 0;
  let output = "";
  let match: RegExpExecArray | null;
  while ((match = MARKDOWN_CODE.exec(content)) !== null) {
    output += transform(content.slice(cursor, match.index));
    output += match[0];
    cursor = match.index + match[0].length;
  }
  return output + transform(content.slice(cursor));
}

function validHttpUrl(value: unknown) {
  const url = typeof value === "string" ? value.trim() : "";
  if (!/^https?:\/\//i.test(url)) {
    return "";
  }
  try {
    return new URL(url).toString();
  } catch {
    return "";
  }
}

function compactSnippet(value: unknown) {
  const text = typeof value === "string" ? value.replace(/\s+/g, " ").trim() : "";
  return text.length > 220 ? `${text.slice(0, 219)}…` : text;
}

export function citationSource(value: unknown): WebCitationSource | null {
  if (!isRecord(value)) {
    return null;
  }
  const citationId = typeof value.citation_id === "string" ? value.citation_id.trim() : "";
  const url = validHttpUrl(value.url);
  if (!citationId || !/^[\w-]+$/.test(citationId) || !url) {
    return null;
  }
  let domain = typeof value.domain === "string" ? value.domain.trim() : "";
  if (!domain) {
    domain = new URL(url).hostname;
  }
  return {
    citationId,
    title: typeof value.title === "string" && value.title.trim() ? value.title.trim() : domain,
    url,
    domain,
    snippet: compactSnippet(value.snippet ?? value.content),
    publishedAt: typeof value.published_at === "string" ? value.published_at : null
  };
}

function citationProjection(
  content: string,
  sources: readonly WebCitationSource[],
  render: (citation: DisplayCitation) => string,
) {
  const byId = new Map(sources.map((source) => [source.citationId, source]));
  const displayBySource = new Map<string, DisplayCitation>();
  const cited: DisplayCitation[] = [];
  const projected = mapMarkdownOutsideCode(content, (text) =>
    text.replace(CITATION_MARKER, (marker, citationId: string, offset: number) => {
      if (offset > 0 && text[offset - 1] === "\\") {
        return marker;
      }
      const source = byId.get(citationId);
      if (!source) {
        return "";
      }
      const sourceKey = source.url || source.citationId;
      let display = displayBySource.get(sourceKey);
      if (!display) {
        display = { ...source, number: cited.length + 1 };
        displayBySource.set(sourceKey, display);
        cited.push(display);
      }
      return render({ ...display, citationId });
    })
  );
  return { content: projected, cited };
}

/** Convert internal markers to Markdown links consumed by MarkdownContent's citation renderer. */
export function projectCitationMarkers(
  content: string,
  sources: readonly WebCitationSource[]
) {
  return citationProjection(
    content,
    sources,
    (citation) => `[${citation.number}](${CITATION_HREF_PREFIX}${encodeURIComponent(citation.citationId)})`
  );
}

function escapeMarkdownLabel(value: string) {
  return value.replace(/\\/g, "\\\\").replace(/\[/g, "\\[").replace(/\]/g, "\\]");
}

/** Copy/export view: keep citations inline while replacing internal IDs with real links. */
export function exportableCitationMarkdown(
  content: string,
  sources: readonly WebCitationSource[]
) {
  return citationProjection(
    content,
    sources,
    (citation) => `[${escapeMarkdownLabel(citation.title)}](<${citation.url}>)`
  ).content;
}
