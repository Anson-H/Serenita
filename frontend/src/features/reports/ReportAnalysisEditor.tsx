import {useResourceDraft} from "../../utils/useResourceDraft";
import {
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
  const [saveError, setSaveError] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);
  const scrollSnapshotRef = useRef<ScrollPositionSnapshot | null>(null);

  const draftState = useResourceDraft({
    resourceKey: `${workspace.reportSaveKey}:analysis`, server: content ?? '', editing,
    save: async next => {
      if (!workspace.canEdit) throw new Error('当前权限无法保存，草稿已保留。');
      const result = await workspace.updateSelectedReportField({field: 'analysis_content', value: next});
      if (!result) throw new Error('保存失败，草稿已保留，请重试。');
      return next;
    }
  });
  const {draft, update: setDraft} = draftState;

  useStatusNotification(saveError || draftState.error, {
    id: "report-analysis-save-error",
    title: "解读结果未保存",
    tone: "error"
  });

  useLayoutEffect(() => {
    if (!editing) return;
    focusWithoutScroll(textareaRef.current);
    restoreScrollPosition(scrollSnapshotRef.current);
    scrollSnapshotRef.current = null;
  }, [editing]);

  async function save(nextDraft: string) {
    setDraft(nextDraft);setSaveError('');
    const revision = draftState.controller.snapshot().revision;
    if (await draftState.flush()) {
      if (revision === draftState.controller.snapshot().revision) setEditing(false);
    }
  }

  function cancel() {
    if (draftState.controller.snapshot().pending) return;
    draftState.controller.cancel();
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
            <div aria-hidden="true" className="text-input-surface report-analysis-markdown report-analysis-size-mirror">
              <MarkdownContent content={draft} />
            </div>
          ) : (
            <div aria-hidden="true" className="text-input-surface report-analysis-markdown report-analysis-size-mirror">
              <strong>暂无解读结果</strong>
            </div>
          )}
          <textarea
            className="text-input-surface"
            aria-label="解读结果 Markdown"
            onBlur={(event) => void save(event.currentTarget.value)}
            onChange={(event) => setDraft(event.target.value)}
            onCompositionStart={() => draftState.controller.composition(true)}
            onCompositionEnd={(event) => {syncCommittedText(event, setDraft); draftState.controller.composition(false);}}
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
      <button aria-label="删除医疗报告" className="control control--secondary control--danger report-delete-button destructive-action-button removal-action-control" disabled={!workspace.canEdit || workspace.deleting} onClick={() => void workspace.deleteSelectedReport()} type="button">
        <TrashIcon className="message-action-icon" />
        <span>{workspace.deleting ? "删除中..." : "删除医疗报告"}</span>
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

type ReportAnalysisEditorWorkspace = Pick<ReportWorkspaceState, "reportSaveKey" | "analyzeSelectedReport" | "analyzing" | "canEdit" | "clearActionFeedback" | "deleteSelectedReport" | "deleting" | "saving" | "updateSelectedReportField">;
