import { useEffect, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import type {
  AddedModel,
  ModelModeCapabilityProfile,
  ModelUpdatePayload
} from "../../api/client";
import { GroupedList } from "../../components/GroupedList";
import {
  AudioFormatIcon,
  CheckIcon,
  DocumentFormatIcon,
  ImageFormatIcon,
  LightningIcon,
  OtherFormatIcon,
  SlidersIcon,
  TextFormatIcon,
  ToolCallingIcon,
  TrashIcon,
  VideoFormatIcon,
  XIcon
} from "../../components/icons";
import { SelectPopover } from "../../components/SelectPopover";
import { useStatusNotification } from "../../components/StatusNotificationCenter";
import { useModalDialog } from "../../components/useModalDialog";
import { createModelEditorActions } from './modelEditorActions';
import type { ModelAutoSaveJob, ModelSettingsDraft } from "./modelSettingsDraft";
import { modelSettingsDraft, modelSettingsPayload, modelSettingsSignature } from "./modelSettingsDraft";
import { remoteModelIdentity } from "./remoteModelPresentation";
import { SettingsListForwardIcon } from "./SettingsPrimitives";

const thinkingModeOptions = [
  { label: "默认", value: "default" },
  { label: "关闭", value: "off" },
  { label: "最小", value: "minimal" },
  { label: "低", value: "low" },
  { label: "中", value: "medium" },
  { label: "高", value: "high" },
  { label: "极高", value: "xhigh" },
  { label: "最高", value: "max" }
] as const;

const mimeTypeGroups: {
  defaultMimeTypes: string[];
  icon: ReactNode;
  key: string;
  label: string;
  matches: (mimeType: string) => boolean;
}[] = [
    {
      defaultMimeTypes: ["image/png"],
      icon: <ImageFormatIcon className="model-capability-option-icon" />,
      key: "image",
      label: "图片",
      matches: (mimeType) => mimeType.startsWith("image/")
    },
    {
      defaultMimeTypes: ["audio/mpeg"],
      icon: <AudioFormatIcon className="model-capability-option-icon" />,
      key: "audio",
      label: "音频",
      matches: (mimeType) => mimeType.startsWith("audio/")
    },
    {
      defaultMimeTypes: ["video/mp4"],
      icon: <VideoFormatIcon className="model-capability-option-icon" />,
      key: "video",
      label: "视频",
      matches: (mimeType) => mimeType.startsWith("video/")
    },
    {
      defaultMimeTypes: ["application/pdf"],
      icon: <DocumentFormatIcon className="model-capability-option-icon" />,
      key: "pdf",
      label: "文档",
      matches: (mimeType) => mimeType === "application/pdf"
    }
  ];

function isStandardMimeType(mimeType: string) {
  return mimeTypeGroups.some((group) => group.matches(mimeType));
}

function modelFormatHint(formats: string[]) {
  return formats.length ? formats.join("、") : undefined;
}

function normalizeMimeTypes(value: string) {
  return [
    ...new Set(
      value
        .split(/[\n,]/)
        .map((item) => item.trim())
        .filter(Boolean)
    )
  ];
}

function summarizeInputCapabilities(profile: ModelModeCapabilityProfile) {
  const mimeTypes = normalizeMimeTypes(profile.file_mime_types.join("\n"));
  const labels = [
    ...(profile.supports_text ? ["文本"] : []),
    ...mimeTypeGroups
      .filter((group) => mimeTypes.some(group.matches))
      .map((group) => group.label),
    ...(mimeTypes.some((mimeType) => !isStandardMimeType(mimeType)) ? ["其它"] : [])
  ];
  return labels.length ? labels.join("、") : "无";
}

function summarizeOutputCapabilities(profile: ModelModeCapabilityProfile) {
  const labels = [
    ...(profile.supports_text ? ["文本"] : []),
    ...(profile.supports_tool_calling ? ["工具调用"] : [])
  ];
  return labels.length ? labels.join("、") : "无";
}

function renderCapabilitySummaryIcons(profile: ModelModeCapabilityProfile) {
  const mimeTypes = normalizeMimeTypes(profile.file_mime_types.join("\n"));
  const entries = [
    ...mimeTypeGroups
      .filter((group) => mimeTypes.some(group.matches))
      .map((group) => ({ icon: group.icon, key: group.key, label: group.label })),
    ...(mimeTypes.some((mimeType) => !isStandardMimeType(mimeType))
      ? [{
        icon: <OtherFormatIcon className="model-capability-option-icon" />,
        key: "other",
        label: "其它"
      }]
      : []),
    ...(profile.supports_tool_calling
      ? [{
        icon: <ToolCallingIcon className="model-capability-option-icon" />,
        key: "tool-calling",
        label: "工具调用"
      }]
      : [])
  ];
  if (!entries.length) return undefined;
  return (
    <span
      aria-label={`支持：${entries.map((entry) => entry.label).join("、")}`}
      className="model-capability-summary-icons"
    >
      {entries.map((entry) => (
        <span aria-hidden="true" key={entry.key}>{entry.icon}</span>
      ))}
    </span>
  );
}

export type ModelSettingsPage = "root" | "thinking" | "format";

function ModelChoiceRow({
  active,
  disabled,
  formatHint,
  icon,
  label,
  onClick
}: {
  active: boolean;
  disabled: boolean;
  formatHint?: string;
  icon?: ReactNode;
  label: ReactNode;
  onClick: () => void;
}) {
  return (
    <button
      aria-pressed={active}
      className="model-capability-choice-row"
      disabled={disabled}
      onClick={onClick}
      title={formatHint}
      type="button"
    >
      <span
        aria-hidden="true"
        className="model-choice-indicator selection-check-control"
        data-selected={active ? "true" : undefined}
      >
        {active ? (
          <CheckIcon className="model-choice-check-icon selection-check-icon" />
        ) : null}
      </span>
      <span className="model-capability-choice-copy">
        {icon ? <span aria-hidden="true">{icon}</span> : null}
        <span>{label}</span>
      </span>
    </button>
  );
}

function ModelCapabilityNavigationRow({
  accessory,
  label,
  onClick
}: {
  accessory?: ReactNode;
  label: string;
  onClick: () => void;
}) {
  return (
    <button
      className="model-capability-navigation-row grouped-labeled-navigation-row"
      onClick={onClick}
      type="button"
    >
      <span>{label}</span>
      <span className="model-capability-navigation-trailing">
        {accessory}
      </span>
      <SettingsListForwardIcon />
    </button>
  );
}

export function ModelSettingsEditor({
  model,
  onDelete,
  page,
  onNavigate,
  onProbe,
  onSave,
  providerAttachmentMimeTypes,
  probing,
  supplierFallbackName,
  saving
}: {
  model: AddedModel;
  onDelete: () => Promise<boolean>;
  page: ModelSettingsPage;
  onNavigate: (page: ModelSettingsPage) => void;
  onProbe: () => void | Promise<void>;
  onSave: (patch: ModelUpdatePayload) => void | Promise<void>;
  providerAttachmentMimeTypes: string[];
  probing: boolean;
  supplierFallbackName: string;
  saving: boolean;
}) {
  const initialDraft = modelSettingsDraft(model);
  const [draft, setDraft] = useState<ModelSettingsDraft>(initialDraft);
  const draftRef = useRef(initialDraft);
  const onSaveRef = useRef(onSave);
  const saveTimerRef = useRef<number | null>(null);
  const saveQueueRef = useRef<ModelAutoSaveJob[]>([]);
  const saveRunningRef = useRef(false);
  const mountedRef = useRef(true);
  const deletingRef = useRef(false);
  const lastSavedPayloadRef = useRef(modelSettingsPayload(initialDraft));
  const lastSavedSignatureRef = useRef(
    modelSettingsSignature(lastSavedPayloadRef.current)
  );
  const [capabilityView, setCapabilityView] = useState<"non_thinking" | "thinking">(
    "non_thinking"
  );
  const [customFormatOpen, setCustomFormatOpen] = useState(false);
  const [customMimeTypeDraft, setCustomMimeTypeDraft] = useState("");
  const customFormatDialogRef = useRef<HTMLDivElement | null>(null);
  const customFormatTextareaRef = useRef<HTMLTextAreaElement | null>(null);
  const [validationError, setValidationError] = useState("");
  const [deleting, setDeleting] = useState(false);
  const {
    modelName,
    thinkingModes,
    capabilityProfiles,
    contextWindowTokens,
    maxOutputTokens
  } = draft;
  const identity = remoteModelIdentity(model.remote_model_id);
  const supplierName = identity.supplier || supplierFallbackName;
  const aggregateProfile: ModelModeCapabilityProfile = {
    availability: "available",
    supports_text:
      capabilityProfiles.non_thinking.supports_text || capabilityProfiles.thinking.supports_text,
    file_mime_types: [
      ...new Set([
        ...capabilityProfiles.non_thinking.file_mime_types,
        ...capabilityProfiles.thinking.file_mime_types
      ])
    ],
    supports_tool_calling:
      capabilityProfiles.non_thinking.supports_tool_calling ||
      capabilityProfiles.thinking.supports_tool_calling
  };
  const visibleProfile = capabilityProfiles[capabilityView];
  const normalizedMimeTypes = normalizeMimeTypes(
    visibleProfile.file_mime_types.join("\n")
  );
  const otherMimeTypes = normalizedMimeTypes.filter(
    (mimeType) => !isStandardMimeType(mimeType)
  );
  useStatusNotification(validationError, {
    id: `model-settings-${model.model_id}-error`,
    title: "模型设置未保存",
    tone: "error"
  });
  useModalDialog({
    active: customFormatOpen,
    dialogRef: customFormatDialogRef,
    initialFocusRef: customFormatTextareaRef,
    onEscape: () => setCustomFormatOpen(false)
  });

  useEffect(() => {
    onSaveRef.current = onSave;
  }, [onSave]);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      if (saveTimerRef.current !== null) {
        window.clearTimeout(saveTimerRef.current);
        saveTimerRef.current = null;
        if (!deletingRef.current) enqueueModelAutoSave(draftRef.current);
      }
    };
  }, []);

  function toggleMimeTypeGroup(group: (typeof mimeTypeGroups)[number]) {
    const enabled = normalizedMimeTypes.some(group.matches);
    const remaining = normalizedMimeTypes.filter((mimeType) => !group.matches(mimeType));
    const providerDefaults = providerAttachmentMimeTypes.filter(group.matches);
    const defaults = providerDefaults.length ? providerDefaults : group.defaultMimeTypes;
    updateVisibleProfile({
      file_mime_types: enabled ? remaining : [...remaining, ...defaults]
    });
  }

  function toggleOtherMimeTypes() {
    if (!otherMimeTypes.length) {
      openCustomFormatDialog();
      return;
    }
    updateVisibleProfile({
      file_mime_types: normalizedMimeTypes.filter(isStandardMimeType)
    });
  }

  function updateVisibleProfile(patch: Partial<ModelModeCapabilityProfile>) {
    scheduleModelDraft((current) => ({
      ...current,
      capabilityProfiles: {
        ...current.capabilityProfiles,
        [capabilityView]: {
          ...current.capabilityProfiles[capabilityView],
          availability: "available",
          ...patch
        }
      }
    }), { immediate: true });
  }

  function openCustomFormatDialog() {
    setCustomMimeTypeDraft(visibleProfile.file_mime_types.join("\n"));
    setCustomFormatOpen(true);
  }

  function saveCustomFormats() {
    updateVisibleProfile({
      file_mime_types: normalizeMimeTypes(customMimeTypeDraft)
    });
    setCustomFormatOpen(false);
  }

  function renderCapabilityModePicker(ariaLabel: string) {
    return (
      <SelectPopover
        ariaLabel={ariaLabel}
        className="model-capability-mode-picker"
        menuWidth="content" menuAlign="end" interactionOwner="row"
        onChange={(value) => setCapabilityView(value)}
        options={[
          { label: "非思考", value: "non_thinking" },
          { label: "思考", value: "thinking" }
        ]}
        value={capabilityView}
      />
    );
  }
  const { enqueueModelAutoSave, scheduleModelDraft, flushScheduledModelSave, deleteModel, probeModel } = createModelEditorActions({
    saveRunningRef,
    saveQueueRef,
    lastSavedSignatureRef,
    lastSavedPayloadRef,
    onSaveRef,
    mountedRef,
    setValidationError,
    draftRef,
    setDraft,
    saveTimerRef,
    deletingRef,
    setDeleting,
    onDelete,
    probing,
    onProbe
  });

  return (
    <form
      className="model-settings-panel-form"
      onSubmit={(event) => event.preventDefault()}
    >
      <div className="model-settings-panel-body scroll-content">
        {page === "root" ? (
          <>
            <div className="model-settings-block model-identity-block">
              <GroupedList as="dl" layout="fields" className="model-source-summary" density="standard">
                <div className="field-row">
                  <dt>模型 ID</dt>
                  <dd title={model.remote_model_id}>{model.remote_model_id}</dd>
                </div>
                <div className="field-row">
                  <dt>供应商</dt>
                  <dd>{supplierName}</dd>
                </div>
                <div className="field-row">
                  <dt>模型</dt>
                  <dd title={identity.model}>{identity.model}</dd>
                </div>
              </GroupedList>
              <GroupedList layout="fields" density="standard">
                <label className="model-settings-field model-name-field field-row">
                  <span>模型名称</span>
                  <input
                    onBlur={flushScheduledModelSave}
                    onChange={(event) => scheduleModelDraft((current) => ({
                      ...current,
                      modelName: event.target.value
                    }))}
                    value={modelName}
                  />
                </label>
              </GroupedList>
            </div>

            <div className="model-settings-block model-capability-navigation-block">
              <h3>能力设置</h3>
              <GroupedList layout="navigation"
                aria-label="能力设置"
                className="model-capability-list"
                density="standard"
              >
                <ModelCapabilityNavigationRow
                  label="思考档位"
                  onClick={() => onNavigate("thinking")}
                />
                <ModelCapabilityNavigationRow
                  accessory={renderCapabilitySummaryIcons(aggregateProfile)}
                  label="输入与输出"
                  onClick={() => onNavigate("format")}
                />
                <button
                  aria-busy={probing}
                  className={`control control--row model-capability-probe-button${probing ? " probing" : ""}`}
                  disabled={probing || deleting}
                  onClick={() => void probeModel()}
                  type="button"
                >
                  <LightningIcon />
                  <span>{probing ? "识别中" : "识别能力"}</span>
                </button>
              </GroupedList>
            </div>

            <div className="model-settings-block model-token-limit-block">
              <h3>词元限制</h3>
              <GroupedList layout="fields" className="model-token-fields" density="standard">
                <label className="model-settings-field field-row">
                  <span>输入词元最大量</span>
                  <input
                    inputMode="numeric"
                    onBlur={flushScheduledModelSave}
                    onChange={(event) => scheduleModelDraft((current) => ({
                      ...current,
                      contextWindowTokens: event.target.value
                    }))}
                    placeholder="留空"
                    type="text"
                    value={contextWindowTokens}
                  />
                </label>
                <label className="model-settings-field field-row">
                  <span>输出词元最大量</span>
                  <input
                    inputMode="numeric"
                    onBlur={flushScheduledModelSave}
                    onChange={(event) => scheduleModelDraft((current) => ({
                      ...current,
                      maxOutputTokens: event.target.value
                    }))}
                    placeholder="留空"
                    type="text"
                    value={maxOutputTokens}
                  />
                </label>
              </GroupedList>
            </div>

            <button
              className="control control--secondary control--danger model-delete-action removal-action-control"
              disabled={deleting || saving}
              onClick={() => void deleteModel()}
              type="button"
            >
              <TrashIcon className="settings-action-icon" />
              <span>{deleting ? "正在删除..." : "删除模型"}</span>
            </button>
          </>
        ) : null}

        {page === "thinking" ? (
          <div className="model-settings-block thinking-mode-block">
            <GroupedList className="model-capability-list thinking-mode-options" selectionMode="multiple" density="standard">
              {thinkingModeOptions.map((mode) => (
                <ModelChoiceRow
                  active={thinkingModes.includes(mode.value)}
                  disabled={false}
                  key={mode.value}
                  label={`${mode.label} ${mode.value}`}
                  onClick={() => scheduleModelDraft((current) => ({
                    ...current,
                    thinkingModes: current.thinkingModes.includes(mode.value)
                      ? current.thinkingModes.filter((item) => item !== mode.value)
                      : [...current.thinkingModes, mode.value]
                  }), { immediate: true })}
                />
              ))}
            </GroupedList>
          </div>
        ) : null}

        {page === "format" ? (
          <div className="model-settings-block model-format-settings">
            <GroupedList as="dl" layout="fields" className="model-source-summary model-capability-summary" density="standard">
              <div className="field-row">
                <dt>输入模态</dt>
                <dd>{summarizeInputCapabilities(aggregateProfile)}</dd>
              </div>
              <div className="field-row">
                <dt>输出格式</dt>
                <dd>{summarizeOutputCapabilities(aggregateProfile)}</dd>
              </div>
            </GroupedList>

            <GroupedList layout="fields" className="model-format-picker-group" density="standard">
              <div className="model-format-block field-row">
                <h3>编辑模式</h3>
                {renderCapabilityModePicker("选择要编辑的模式")}
              </div>
            </GroupedList>

            <div className="model-format-block">
              <h3>输入模态</h3>
              <GroupedList className="model-capability-list model-input-options" selectionMode="multiple" density="standard">
                <ModelChoiceRow
                  active={visibleProfile.supports_text}
                  disabled={false}
                  icon={<TextFormatIcon className="model-capability-option-icon" />}
                  label="文本"
                  onClick={() => updateVisibleProfile({
                    supports_text: !visibleProfile.supports_text
                  })}
                />
                {mimeTypeGroups.map((group) => {
                  const exactFormats = normalizedMimeTypes.filter(group.matches);
                  const active = exactFormats.length > 0;
                  return (
                    <ModelChoiceRow
                      active={active}
                      disabled={false}
                      formatHint={modelFormatHint(exactFormats)}
                      icon={group.icon}
                      key={group.key}
                      label={group.label}
                      onClick={() => toggleMimeTypeGroup(group)}
                    />
                  );
                })}
                <ModelChoiceRow
                  active={otherMimeTypes.length > 0}
                  disabled={false}
                  formatHint={modelFormatHint(otherMimeTypes)}
                  icon={<OtherFormatIcon className="model-capability-option-icon" />}
                  label="其它"
                  onClick={toggleOtherMimeTypes}
                />
                <button
                  className="model-capability-navigation-row model-detail-customize-button"
                  onClick={openCustomFormatDialog}
                  title="编辑全部输入格式"
                  type="button"
                >
                  <span className="model-capability-choice-copy">
                    <SlidersIcon className="model-capability-option-icon" />
                    <span>详细自定义</span>
                  </span>
                  <SettingsListForwardIcon />
                </button>
              </GroupedList>
            </div>

            <div className="model-format-block">
              <h3>输出格式</h3>
              <GroupedList className="model-capability-list model-output-options" selectionMode="multiple" density="standard">
                <ModelChoiceRow
                  active={visibleProfile.supports_text}
                  disabled={false}
                  icon={<TextFormatIcon className="model-capability-option-icon" />}
                  label="文本"
                  onClick={() => updateVisibleProfile({
                    supports_text: !visibleProfile.supports_text
                  })}
                />
                <ModelChoiceRow
                  active={visibleProfile.supports_tool_calling}
                  disabled={false}
                  formatHint={visibleProfile.supports_tool_calling
                    ? "原生工具调用"
                    : undefined}
                  icon={<ToolCallingIcon className="model-capability-option-icon" />}
                  label="工具调用"
                  onClick={() => updateVisibleProfile({
                    supports_tool_calling: !visibleProfile.supports_tool_calling
                  })}
                />
              </GroupedList>
            </div>
          </div>
        ) : null}
      </div>
      {customFormatOpen ? createPortal(
        <div
          className="model-format-modal-backdrop dialog-viewport-backdrop"
          onMouseDown={(event) => {
            if (event.currentTarget === event.target) setCustomFormatOpen(false);
          }}
        >
          <div
            aria-labelledby="model-format-dialog-title"
            aria-modal="true"
            className="model-format-modal dialog-viewport-surface dialog-title-ellipsis"
            ref={customFormatDialogRef}
            role="dialog"
            tabIndex={-1}
          >
            <header className="dialog-titlebar model-format-modal-header">
              <h2 id="model-format-dialog-title">详细自定义</h2>
              <button
                aria-label="关闭详细自定义"
                className="control control--titlebar control--icon control--ghost icon-action-control secondary-button settings-icon-button titlebar-icon-control"
                onClick={() => setCustomFormatOpen(false)}
                type="button"
              >
                <XIcon />
              </button>
            </header>
            <div className="dialog-body model-format-modal-body scroll-content">
              <label className="model-format-modal-field">
                <span>MIME 类型</span>
                <textarea
                  aria-label="精确编辑 MIME 类型"
                  onChange={(event) => setCustomMimeTypeDraft(event.target.value)}
                  placeholder="每行一个，例如 image/png"
                  ref={customFormatTextareaRef}
                  rows={8}
                  value={customMimeTypeDraft}
                />
              </label>
            </div>
            <footer className="model-format-modal-footer dialog-action-bar">
              <button
                className="control control--secondary text-button control-primary dialog-secondary-action"
                onClick={() => setCustomFormatOpen(false)}
                type="button"
              >
                <XIcon />
                <span>取消</span>
              </button>
              <button
                className="control control--primary command-button control-primary dialog-primary-action"
                onClick={saveCustomFormats}
                type="button"
              >
                <CheckIcon />
                <span>完成</span>
              </button>
            </footer>
          </div>
        </div>,
        document.body
      ) : null}
    </form>
  );
}
