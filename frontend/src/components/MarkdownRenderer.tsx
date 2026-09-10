import { useMemo } from "react";
import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";

import {
  CITATION_HREF_PREFIX,
  projectCitationMarkers,
  type WebCitationSource
} from "../utils/markdownCitations";

export type MarkdownRendererProps = {
  className?: string;
  annotationSourceId?: string;
  content: string;
  citationSources?: readonly WebCitationSource[];
  processCitations?: boolean;
};

function citationIdFromHref(href: string | undefined) {
  if (!href?.startsWith(CITATION_HREF_PREFIX)) return null;
  try {
    return decodeURIComponent(href.slice(CITATION_HREF_PREFIX.length));
  } catch {
    return null;
  }
}

function markdownComponents(citationSources: readonly WebCitationSource[]): Components {
  const citationsById = new Map(
    citationSources.map((citation) => [citation.citationId, citation])
  );
  return {
    a({ node: _node, href, ...props }) {
      const citationId = citationIdFromHref(href);
      const citation = citationId ? citationsById.get(citationId) : undefined;
      if (citation) {
        const sourceLabel = citation.domain
          ? `${citation.title}（${citation.domain}）`
          : citation.title;
        return (
          <a
            {...props}
            aria-label={`来源：${sourceLabel}`}
            className="citation-link"
            data-citation-id={citation.citationId}
            href={citation.url}
            rel="noopener noreferrer"
            target="_blank"
            title={`来源：${sourceLabel}`}
          >
            <sup>{props.children}</sup>
          </a>
        );
      }
      const external = typeof href === "string" && /^https?:\/\//i.test(href);
      return (
        <a
          {...props}
          href={href}
          rel={external ? "noopener noreferrer" : undefined}
          target={external ? "_blank" : undefined}
        />
      );
    },
    table({ node: _node, ...props }) {
      return (
        <div
          aria-label="可横向滚动的数据表格"
          className="markdown-table-scroll"
          role="region"
          tabIndex={0}
        >
          <table {...props} />
        </div>
      );
    },
    th({ node: _node, ...props }) {
      return <th scope="col" {...props} />;
    },
    img({ node: _node, alt = "", ...props }) {
      return <img {...props} alt={alt} decoding="async" loading="lazy" />;
    }
  };
}

export function MarkdownRenderer({
  className = "",
  annotationSourceId,
  content,
  citationSources = [],
  processCitations = false
}: MarkdownRendererProps) {
  const projectedContent = useMemo(
    () => processCitations
      ? projectCitationMarkers(content, citationSources).content
      : content,
    [citationSources, content, processCitations]
  );
  const components = useMemo(
    () => markdownComponents(citationSources),
    [citationSources]
  );
  return (
    <div
      className={["markdown-content", className].filter(Boolean).join(" ")}
      data-annotation-source-id={annotationSourceId}
    >
      <ReactMarkdown components={components} remarkPlugins={[remarkGfm]}>
        {projectedContent}
      </ReactMarkdown>
    </div>
  );
}
