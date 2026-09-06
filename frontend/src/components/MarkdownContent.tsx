import { lazy, Suspense } from "react";
import type { MarkdownRendererProps } from "./MarkdownRenderer";


type MarkdownContentProps = MarkdownRendererProps;

const MarkdownRenderer = lazy(() => import("./MarkdownRenderer").then(
  ({ MarkdownRenderer: Component }) => ({ default: Component })
));

export function MarkdownContent({
  annotationSourceId,
  content,
  citationSources = [],
  processCitations = false
}: MarkdownContentProps) {
  return (
    <Suspense
      fallback={(
        <div
          aria-busy="true"
          className="markdown-content markdown-content-loading"
          data-annotation-source-id={annotationSourceId}
        >
          {content}
        </div>
      )}
    >
      <MarkdownRenderer
        annotationSourceId={annotationSourceId}
        citationSources={citationSources}
        content={content}
        processCitations={processCitations}
      />
    </Suspense>
  );
}
