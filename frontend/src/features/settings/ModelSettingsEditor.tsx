import { ModelCapabilityNavigationRow } from "./ModelCapabilityNavigationRow";
import { ModelChoiceRow } from "./ModelChoiceRow";
import { ModelInputModalityEditor } from "./ModelInputModalityEditor";
import { mimeTypeGroups, isStandardMimeType, ModelCapabilitySummaryIcons } from "./ModelCapabilitySummary";
import { isGenerationModel } from "../modelConfiguration/generationModels";
import { ModelTypeSelector, EmbeddingSettingsEditor } from "./EmbeddingSettingsEditor";
import { navigationLabels } from "../../components/navigationLabels";
import { useEffect, useRef, useState } from "react";
import type {
  AddedModel,
  GenerationModel,
  ModelModeCapabilityProfile,
  ModelUpdatePayload
} from "../../api/client";
import { GroupedList } from "../../components/GroupedList";
import {
  LightningIcon,
  TextFormatIcon,
  ToolCallingIcon,
  TrashIcon,
} from "../../components/icons";
import { SelectPopover } from "../../components/SelectPopover";
import { useStatusNotification } from "../../components/StatusNotificationCenter";
import { createModelEditorActions } from './modelEditorActions';
import type { ModelAutoSaveJob, ModelSettingsDraft } from "./modelSettingsDraft";
import { modelSettingsDraft, modelSettingsPayload, modelSettingsSignature } from "./modelSettingsDraft";
import { ModelIdentitySection } from "./ModelIdentitySection";

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

function summarizeInputCapabilities(profile: ModelModeCapabilityProfile) {
  const mimeTypes = profile.file_mime_types;
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

export type ModelSettingsPage = "root" | "thinking" | "inputOutput";

type EditorProps = Omit<Parameters<typeof GenerationSettingsEditor>[0], "model"> & { model: AddedModel };
export function ModelSettingsEditor(props: EditorProps) {
  return isGenerationModel(props.model)
      ? <GenerationSettingsEditor {...props} model={props.model} />
      : <EmbeddingSettingsEditor supplierFallbackName={props.supplierFallbackName} page={props.page} onNavigate={props.onNavigate} providerAttachmentMimeTypes={props.providerAttachmentMimeTypes} model={props.model} onSave={props.onSave} onProbe={props.onProbe} onDelete={props.onDelete} probing={props.probing} saving={props.saving} />;
}

function GenerationSettingsEditor({
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
  model: GenerationModel;
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
  const [validationError, setValidationError] = useState("");
  const [deleting, setDeleting] = useState(false);
  const {
    modelName,
    thinkingModes,
    capabilityProfiles,
    contextWindowTokens,
    maxOutputTokens
  } = draft;
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
  useStatusNotification(validationError, {
    id: `model-settings-${model.model_id}-error`,
    title: "模型设置未保存",
    tone: "error"
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
      <div className="model-settings-panel-body scroll-content content-column">
        {page === "root" ? (
          <>
            <ModelIdentitySection remoteModelId={model.remote_model_id} supplierFallbackName={supplierFallbackName}>
                <label className="model-settings-field model-name-field field-row">
                  <span>模型昵称</span>
                  <input
                    onBlur={flushScheduledModelSave}
                    onChange={(event) => scheduleModelDraft((current) => ({
                      ...current,
                      modelName: event.target.value
                    }))}
                    value={modelName}
                  />
                </label>
            </ModelIdentitySection>

            <div className="model-settings-block model-capability-navigation-block">
              <h3>能力设置</h3>
              <GroupedList layout="navigation"
                aria-label="能力设置"
                className="model-capability-list"
                density="standard"
              >
                <ModelTypeSelector model={model} onSave={onSave} saving={saving} />
                <ModelCapabilityNavigationRow
                  label={navigationLabels.thinking}
                  onClick={() => onNavigate("thinking")}
                />
                <ModelCapabilityNavigationRow
                  accessory={<ModelCapabilitySummaryIcons profile={aggregateProfile} direction="input" />}
                  label={navigationLabels.inputOutput}
                  onClick={() => onNavigate("inputOutput")}
                />
              </GroupedList>
            </div>

            <div className="model-settings-block model-token-limit-block">
              <h3>词元限制</h3>
              <GroupedList layout="fields" className="model-token-fields" density="standard">
                <label className="model-settings-field field-row">
                  <span>单条输入词元上限</span>
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
                  <span>单条输出词元上限</span>
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
              aria-busy={probing}
              className={`control control--secondary model-capability-probe-button${probing ? " probing" : ""}`}
              disabled={deleting}
              onClick={() => void probeModel()}
              type="button"
            >
              <LightningIcon />
              <span>{probing ? "检测中" : "检测模型"}</span>
            </button>

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

        {page === "inputOutput" ? (
          <div className="model-settings-block model-format-settings">
            <GroupedList as="dl" layout="fields" className="model-source-summary model-capability-summary" density="standard">
              <div className="field-row">
                <dt>{navigationLabels.inputModalities}</dt>
                <dd>{summarizeInputCapabilities(aggregateProfile)}</dd>
              </div>
              <div className="field-row">
                <dt>{navigationLabels.outputFormats}</dt>
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
              <h3>{navigationLabels.inputModalities}</h3>
              <ModelInputModalityEditor
                supportsText={visibleProfile.supports_text}
                mimeTypes={visibleProfile.file_mime_types}
                providerMimeTypes={providerAttachmentMimeTypes}
                onChange={updateVisibleProfile}
              />
            </div>

            <div className="model-format-block">
              <h3>{navigationLabels.outputFormats}</h3>
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

    </form>
  );
}
