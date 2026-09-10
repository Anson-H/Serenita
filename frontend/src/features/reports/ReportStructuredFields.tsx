import {
  useLayoutEffect,
  useRef,
  useState,
  type ReactNode,
  type RefObject
} from "react";
import {
  type ExaminationReport,
  type PathologyReport,
  type ReportDetail,
  type ReportEditableField,
  type SurgeryReport
} from "../../api/client";
import { GroupedList } from "../../components/GroupedList";
import { ENTRY_FIELDS } from "./reportFields";
import type { InlineInputKind } from "./ReportInlineField";
import { InlineEditableValue } from "./ReportInlineField";
import { LabResults } from "./ReportLabResults";
import {
  formatReportDate
} from "./reportPresentation";
import type { ReportWorkspaceState } from "./useReportWorkspace";

type DefinitionField = {
  field: ReportEditableField;
  inputKind?: InlineInputKind;
  key: string;
  label: string;
  value?: string | null;
};

function synchronizeStructuredDefinitionRows(definition: HTMLDListElement) {
  const rows = Array.from(definition.querySelectorAll<HTMLElement>(".structured-field"));
  rows.forEach((row) => {
    row.style.height = "auto";
  });

  rows.forEach((row) => {
    const label = row.querySelector<HTMLElement>(".field-label");
    const content = row.querySelector<HTMLElement>(
      ".report-inline-edit-size-mirror > span:first-child, .report-inline-edit-trigger > span:first-child, .report-inline-edit > input, .date-time-anchor"
    );
    if (!label || !content) return;

    const rowStyle = window.getComputedStyle(row);
    const contentStyle = window.getComputedStyle(content);
    const lineHeight = Number.parseFloat(contentStyle.lineHeight);
    const contentRect = content.getBoundingClientRect();
    const renderedLines = Number.isFinite(lineHeight) && lineHeight > 0
      ? Math.max(1, Math.ceil((contentRect.height - 0.5) / lineHeight))
      : 1;
    const contentHeight = Number.isFinite(lineHeight)
      ? renderedLines * lineHeight
      : contentRect.height;
    const labelHeight = label.getBoundingClientRect().height;
    const paddingTop = Number.parseFloat(rowStyle.paddingTop) || 0;
    const paddingBottom = Number.parseFloat(rowStyle.paddingBottom) || 0;
    const minHeight = Number.parseFloat(rowStyle.minHeight) || 0;

    row.style.height = `${Math.max(
      minHeight,
      Math.ceil(Math.max(labelHeight, contentHeight) + paddingTop + paddingBottom)
    )}px`;
  });
}

function useStructuredDefinitionRowMeasurements(ref: RefObject<HTMLDListElement | null>) {
  useLayoutEffect(() => {
    const definition = ref.current;
    if (!definition) return;

    const synchronize = () => synchronizeStructuredDefinitionRows(definition);
    let observedWidth = definition.getBoundingClientRect().width;
    synchronize();

    const resizeObserver = typeof ResizeObserver === "undefined"
      ? null
      : new ResizeObserver(() => {
        const nextWidth = definition.getBoundingClientRect().width;
        if (Math.abs(nextWidth - observedWidth) <= 0.5) return;
        observedWidth = nextWidth;
        synchronize();
      });
    resizeObserver?.observe(definition);

    const mutationObserver = typeof MutationObserver === "undefined"
      ? null
      : new MutationObserver(synchronize);
    mutationObserver?.observe(definition, {
      characterData: true,
      childList: true,
      subtree: true
    });

    window.addEventListener("resize", synchronize);
    window.visualViewport?.addEventListener("resize", synchronize);
    return () => {
      resizeObserver?.disconnect();
      mutationObserver?.disconnect();
      window.removeEventListener("resize", synchronize);
      window.visualViewport?.removeEventListener("resize", synchronize);
    };
  }, [ref]);
}

function StructuredDefinition({
  fields,
  workspace
}: {
  fields: DefinitionField[];
  workspace: ReportStructuredFieldsWorkspace;
}) {
  const definitionRef = useRef<HTMLDListElement | null>(null);
  useStructuredDefinitionRowMeasurements(definitionRef);
  return (
    <GroupedList as="dl" layout="fields" className="structured-definition" ref={definitionRef} density="standard">
      {fields.map((field) => (
        <div className="structured-field field-row" key={field.key}>
          <dt className="field-label">{field.label}</dt>
          <dd className="field-value">
            <InlineEditableValue
              displayValue={field.inputKind === "datetime-local" && field.value
                ? formatReportDate(field.value, true)
                : undefined}
              field={field.field}
              inputKind={field.inputKind ?? "text"}
              label={field.label}
              value={field.value}
              workspace={workspace}
            />
          </dd>
        </div>
      ))}
    </GroupedList>
  );
}

function ExaminationContent({ result, workspace }: { result?: ExaminationReport | null; workspace: ReportStructuredFieldsWorkspace }) {
  return <StructuredDefinition workspace={workspace} fields={(ENTRY_FIELDS["检查报告"] ?? []).map(field => ({
    key: field.key, field: field.key, label: field.label,
    inputKind: field.type === "datetime-local" ? "datetime-local" as const : field.textarea ? "textarea" as const : undefined,
    value: result?.[field.key as keyof typeof result]
  }))} />;
}

function PathologyContent({ result, workspace }: { result?: PathologyReport | null; workspace: ReportStructuredFieldsWorkspace }) {
  return <StructuredDefinition workspace={workspace} fields={(ENTRY_FIELDS["病理报告"] ?? []).map(field => ({
    key: field.key, field: field.key, label: field.label,
    inputKind: field.type === "datetime-local" ? "datetime-local" as const : field.textarea ? "textarea" as const : undefined,
    value: result?.[field.key as keyof typeof result]
  }))} />;
}

function SurgeryContent({ result, workspace }: { result?: SurgeryReport | null; workspace: ReportStructuredFieldsWorkspace }) {
  return <StructuredDefinition workspace={workspace} fields={(ENTRY_FIELDS["手术报告"] ?? []).map(field => ({
    key: field.key, field: field.key, label: field.label,
    inputKind: field.type === "datetime-local" ? "datetime-local" as const : field.textarea ? "textarea" as const : undefined,
    value: result?.[field.key as keyof typeof result]
  }))} />;
}

export function StructuredReportContent({ report, workspace }: { report: ReportDetail; workspace: ReportStructuredFieldsWorkspace }) {
  const [addingLabItem, setAddingLabItem] = useState(false);
  const addLabItemTriggerRef = useRef<HTMLButtonElement | null>(null);
  let content: ReactNode;
  let heading: string;
  if (report.report_type === "检验报告") {
    heading = "检验结果";
    content = (
      <LabResults
        addTriggerRef={addLabItemTriggerRef}
        adding={addingLabItem}
        onAddingChange={setAddingLabItem}
        report={report}
        workspace={workspace}
      />
    );
  } else if (report.report_type === "检查报告") {
    heading = "检查结果";
    content = <ExaminationContent result={report.examination_report} workspace={workspace} />;
  } else if (report.report_type === "病理报告") {
    heading = "病理结果";
    content = <PathologyContent result={report.pathology_report} workspace={workspace} />;
  } else if (report.report_type === "手术报告") {
    heading = "手术记录";
    content = <SurgeryContent result={report.surgery_report} workspace={workspace} />;
  } else if (report.report_type === "门诊病历" || report.report_type === "急诊病历") {
    heading = report.report_type;
    const result = report.report_type === "门诊病历" ? report.outpatient_report : report.emergency_report;
    content = <StructuredDefinition workspace={workspace} fields={(ENTRY_FIELDS[report.report_type] ?? []).map(field => ({
      key: field.key, field: field.key, label: field.label, inputKind: "textarea",
      value: (result as Record<string, string | null> | null)?.[field.key]
    }))} />;
  } else {
    heading = "医疗报告内容";
    const body = report.other_report?.report_body;
    content = (
      <GroupedList className="structured-definition" density="standard">
        <div className="structured-field field-row report-body-row">
          <div className="field-value">
            <InlineEditableValue field="report_body" inputKind="textarea" label="医疗报告内容" required value={body} workspace={workspace} />
          </div>
        </div>
      </GroupedList>
    );
  }
  return (
    <section className="report-section report-structured" aria-labelledby="report-structured-heading">
      <div className="group-heading">
        <h3 id="report-structured-heading">{heading}</h3>
      </div>
      <div className="report-section-body report-structured-body">
        {content}
      </div>
    </section>
  );
}

type ReportStructuredFieldsWorkspace = Pick<ReportWorkspaceState, "reportSaveKey" | "addSelectedReportLabItem" | "canEdit" | "clearActionFeedback" | "deleteSelectedReportLabItem" | "labItemMutation" | "memberId" | "saving" | "updateSelectedReportField">;
