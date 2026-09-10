import { useId, type ReactNode } from "react";

import { MarkdownContent } from "../../components/MarkdownContent";

export function ReportAnalysisMarkdown({
  actions,
  content,
  onEdit
}: {
  actions?: ReactNode;
  content?: string | null;
  onEdit?: (element: HTMLElement) => void;
}) {
  const headingId = `report-analysis-${useId()}`;
  const markdown = content?.trim() ?? "";
  const editable = Boolean(onEdit);

  return (
    <section className="report-section report-analysis" aria-labelledby={headingId}>
      <div className="group-heading report-analysis-heading">
        <h3 id={headingId}>解读结果</h3>
        {actions ? <div className="report-analysis-actions">{actions}</div> : null}
      </div>
      <div className="report-section-body report-analysis-body">
        {markdown ? (
          <div
            aria-label={editable ? "编辑解读结果" : undefined}
            className="text-input-surface report-analysis-markdown"
            onClick={(event) => onEdit?.(event.currentTarget)}
            onKeyDown={editable ? (event) => {
              if (event.key === "Enter" || event.key === " ") {
                event.preventDefault();
                onEdit?.(event.currentTarget);
              }
            } : undefined}
            role={editable ? "button" : undefined}
            tabIndex={editable ? 0 : undefined}
          >
            <MarkdownContent content={markdown} />
          </div>
        ) : (
          <div
            aria-label={editable ? "添加解读结果" : undefined}
            className="text-input-surface report-analysis-markdown"
            onClick={(event) => onEdit?.(event.currentTarget)}
            onKeyDown={editable ? (event) => {
              if (event.key === "Enter" || event.key === " ") {
                event.preventDefault();
                onEdit?.(event.currentTarget);
              }
            } : undefined}
            role={editable ? "button" : undefined}
            tabIndex={editable ? 0 : undefined}
          >
            <strong>暂无解读结果</strong>
          </div>
        )}
      </div>
    </section>
  );
}
