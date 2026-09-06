import {
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
  type ReactNode
} from "react";
import {
  BrainIcon,
  TrashIcon
} from "../../components/icons";
import { MarkdownContent } from "../../components/MarkdownContent";
import { useStatusNotification } from "../../components/StatusNotificationCenter";
import type { ScrollPositionSnapshot } from "../../utils/inputMethod";
import {
  captureScrollPosition,
  focusWithoutScroll,
  isImeComposing,
  restoreScrollPosition,
  syncCommittedText
} from "../../utils/inputMethod";
import { ReportAnalysisMarkdown } from "./ReportAnalysisMarkdown";
import type { ReportWorkspaceState } from "./useReportWorkspace";

export function EditableAnalysis({ actions, content, workspace }: {
  actions: ReactNode;
  content?: string | null;
  workspace: ReportAnalysisEditorWorkspace;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(content ?? "");
  const [saveError, setSaveError] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);
  const scrollSnapshotRef = useRef<ScrollPositionSnapshot | null>(null);

  useStatusNotification(saveError, {
    id: "report-analysis-save-error",
    title: "解读结果未保存",
    tone: "error"
  });

  useEffect(() => {
    setDraft(content ?? "");
    setEditing(false);
    setSaveError("");
  }, [content]);

  useLayoutEffect(() => {
    if (!editing) return;
    focusWithoutScroll(textareaRef.current);
    restoreScrollPosition(scrollSnapshotRef.current);
    scrollSnapshotRef.current = null;
  }, [editing]);

  async function save(nextDraft: string) {
    if (!workspace.canEdit || workspace.saving) return;
    if (nextDraft === (content ?? "")) {
      workspace.clearActionFeedback();
      setSaveError("");
      setEditing(false);
      return;
    }
    setSaveError("");
    const response = await workspace.updateSelectedReportField({
      field: "analysis_content",
      value: nextDraft
    });
    if (response) {
      setEditing(false);
      return;
    }
    setSaveError("保存失败，请检查后重试。");
  }

  function cancel() {
    setDraft(content ?? "");
    setSaveError("");
    setEditing(false);
  }

  if (!editing || !workspace.canEdit) {
    return (
      <ReportAnalysisMarkdown
        actions={actions}
        content={content}
        onEdit={workspace.canEdit ? (element) => {
          scrollSnapshotRef.current = captureScrollPosition(
            element.closest<HTMLElement>(".report-detail-scroll")
          );
          workspace.clearActionFeedback();
          setSaveError("");
          setEditing(true);
        } : undefined}
      />
    );
  }
  return (
    <section className="report-section report-analysis" aria-labelledby="report-analysis-edit-heading">
      <div className="group-heading report-analysis-heading"><h3 id="report-analysis-edit-heading">解读结果</h3><div className="report-analysis-actions">{actions}</div></div>
      <div className="report-section-body report-analysis-body">
        <div
          className="report-analysis-editor report-content-sized-editor"
        >
          {draft.trim() ? (
            <div aria-hidden="true" className="report-analysis-markdown report-analysis-size-mirror">
              <MarkdownContent content={draft} />
            </div>
          ) : (
            <div aria-hidden="true" className="report-subtle-empty report-analysis-size-mirror">
              <strong>暂无解读结果</strong>
            </div>
          )}
          <textarea
            aria-label="解读结果 Markdown"
            onBlur={(event) => void save(event.currentTarget.value)}
            onChange={(event) => setDraft(event.target.value)}
            onCompositionEnd={(event) => syncCommittedText(event, setDraft)}
            onKeyDown={(event) => {
              if (isImeComposing(event)) return;
              if (event.key === "Escape") {
                event.preventDefault();
                cancel();
              }
              if (event.key === "Enter" && (event.metaKey || event.ctrlKey)) {
                event.preventDefault();
                event.currentTarget.blur();
              }
            }}
            ref={textareaRef}
            rows={1}
            value={draft}
          />
        </div>
      </div>
    </section>
  );
}

export function DeleteReportAction({ workspace }: { workspace: ReportAnalysisEditorWorkspace }) {
  return (
    <footer className="report-full-width-action-footer report-delete-footer">
      <button aria-label="删除报告" className="control control--secondary control--danger report-delete-button destructive-action-button removal-action-control" disabled={!workspace.canEdit || workspace.deleting} onClick={() => void workspace.deleteSelectedReport()} type="button">
        <TrashIcon className="message-action-icon" />
        <span>{workspace.deleting ? "删除中..." : "删除报告"}</span>
      </button>
    </footer>
  );
}

export function StartReportAnalysisAction({ analysisRunning, workspace }: {
  analysisRunning: boolean;
  workspace: ReportAnalysisEditorWorkspace;
}) {
  return (
    <footer className="report-full-width-action-footer report-analysis-start-footer">
      <button className="control control--primary command-button control-primary" disabled={!workspace.canEdit || workspace.analyzing || analysisRunning} onClick={() => void workspace.analyzeSelectedReport("initial")} type="button">
        <BrainIcon />
        <span>{analysisRunning ? "解读中..." : "开始解读"}</span>
      </button>
    </footer>
  );
}

type ReportAnalysisEditorWorkspace = Pick<ReportWorkspaceState, "analyzeSelectedReport" | "analyzing" | "canEdit" | "clearActionFeedback" | "deleteSelectedReport" | "deleting" | "saving" | "updateSelectedReportField">;
