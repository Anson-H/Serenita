import { ModelIdentitySection } from "./ModelIdentitySection";
import type { ModelSettingsPage } from "./ModelSettingsEditor";
import { ModelInputModalityEditor } from "./ModelInputModalityEditor";
import { ModelCapabilityNavigationRow } from "./ModelCapabilityNavigationRow";
import { AddedModelCapabilityIcons } from "./ModelCapabilitySummary";
import { navigationLabels } from "../../components/navigationLabels";
import { LightningIcon } from "../../components/icons";
import { useEffect, useRef, useState } from "react";
import type { AddedModel, ModelUpdatePayload, ModelType, EmbeddingCapabilities } from "../../api/modelTypes";
import { GroupedList } from "../../components/GroupedList";
import { SelectPopover } from "../../components/SelectPopover";
import { modelTypeLabels } from "../modelConfiguration/modelEligibility";

type Save = (patch: ModelUpdatePayload) => void | Promise<void>;
const statusLabels = { supported: "支持", unsupported: "不支持", unverified: "暂未验证", not_applicable: "不适用" };

export function ModelTypeSelector({ model, onSave, saving }: { model: AddedModel; onSave: Save; saving: boolean }) {
  const [error, setError] = useState("");
  return <div className="field-row model-type-selector">
      <span>模型类型</span>
      <SelectPopover interactionOwner="row" disabled={saving} menuWidth="content" menuAlign="end" ariaLabel="模型类型" value={model.model_type} options={Object.entries(modelTypeLabels).map(([value, label]) => ({ value: value as ModelType, label }))}
        onChange={async value => { if (saving) return; try { await onSave({ model_type: value as ModelType }); setError(""); } catch (cause) { setError(cause instanceof Error ? cause.message : "类型保存失败。"); } }} />
    {error && <p className="model-type-error" role="alert">{error}</p>}
  </div>;
}

export function EmbeddingSettingsEditor({ model, onSave, onProbe, onDelete, probing, saving, page, onNavigate, providerAttachmentMimeTypes, supplierFallbackName }: {
  supplierFallbackName: string;
  page: ModelSettingsPage; onNavigate: (page: ModelSettingsPage) => void; providerAttachmentMimeTypes: string[];
  model: AddedModel; onSave: Save; onProbe: () => void | Promise<void>; onDelete: () => Promise<boolean>; probing: boolean; saving: boolean;
}) {
  const [error, setError] = useState("");
  const [draft, setDraft] = useState(() => fields(model));
  const [savingOutput, setSavingOutput] = useState(false);
  const current = useRef(draft);
  const pending = useRef(Promise.resolve());
  const previousModel = useRef(model);
  useEffect(() => {
    const previous = fields(previousModel.current);
    const next = fields(model);
    for (const key of Object.keys(next) as (keyof typeof next)[]) {
      if (current.current[key] !== previous[key]) next[key] = current.current[key];
    }
    previousModel.current = model;
    current.current = next; setDraft(next);
  }, [model]);
  function fields(value: AddedModel) { return { model_name: value.model_name, embedding_dimensions: value.embedding_dimensions?.toString() ?? "", max_input_tokens: value.max_input_tokens?.toString() ?? "", max_batch_size: value.max_batch_size?.toString() ?? "" }; }
  function saveField(key: keyof typeof draft) {
    const value = current.current[key].trim();
    if (key === "model_name" && !value) { setError("模型昵称不能为空。"); return; }
    if (key !== "model_name" && value && (!/^\d+$/.test(value) || !Number.isSafeInteger(Number(value)) || Number(value) <= 0)) { setError("参数必须为正整数或留空。"); return; }
    const normalized = key === "model_name" ? value : value ? Number(value) : null;
    if (normalized === model[key]) return;
    pending.current = pending.current.then(async () => { await onSave({ [key]: normalized }); setError(""); }).catch(cause => setError(cause instanceof Error ? cause.message : "保存失败。"));
  }
  function input(key: keyof typeof draft, label: string) {
    return <label className="model-settings-field field-row" key={key}><span>{label}</span><input aria-label={label} inputMode={key === "model_name" ? "text" : "numeric"} value={draft[key]} placeholder="留空"
      onChange={event => { current.current = { ...current.current, [key]: event.target.value }; setDraft(current.current); }} onBlur={() => saveField(key)} /></label>;
  }
  const caps: EmbeddingCapabilities = model.embedding_capabilities ?? { supports_text: false, file_mime_types: [], independent: "unverified", fusion: "unverified", dimensions: {}, protocol: null };
  function saveCapabilities(patch: Partial<Pick<EmbeddingCapabilities, "supports_text" | "file_mime_types" | "independent" | "fusion">>) {
    const save = pending.current.then(() => onSave({ embedding_capabilities: { ...caps, ...patch } }));
    pending.current = save.catch(() => {});
    return save;
  }
  return <div className="model-settings-panel-form" key={model.model_id}><div className="model-settings-panel-body scroll-content content-column">
    {page === "root" ? <>
    <ModelIdentitySection remoteModelId={model.remote_model_id} supplierFallbackName={supplierFallbackName}>
      {input("model_name", "模型昵称")}
    </ModelIdentitySection>
    <div className="model-settings-block model-capability-navigation-block"><h3>能力设置</h3>
      <GroupedList layout="navigation" className="model-capability-list" aria-label="能力设置" density="standard">
        <ModelTypeSelector model={model} onSave={onSave} saving={saving} />
        {model.model_type === "embedding" ? <ModelCapabilityNavigationRow label={navigationLabels.inputOutput} onClick={() => onNavigate("inputOutput")} accessory={<AddedModelCapabilityIcons model={model} />} /> : null}
      </GroupedList>
    </div>
    {model.model_type === "unknown" ? <p>类型尚未确认。可以重新检测，或选择模型类型后编辑参数。</p> : <>
      <div className="model-settings-block"><h3>输入限制</h3><GroupedList layout="fields" density="standard">
        {input("max_input_tokens", "单条输入词元上限")}{input("max_batch_size", "批量输入上限")}
      </GroupedList></div>
    </>}
    {error && <p role="alert">{error}</p>}
    <button aria-busy={probing} className={`control control--secondary model-capability-probe-button${probing ? " probing" : ""}`} type="button" disabled={!probing && (saving || !!error)} onClick={async () => { if (!probing) await pending.current; await onProbe(); }}><LightningIcon /><span>{probing ? "检测中" : "检测模型"}</span></button>
    <button className="control control--secondary control--danger model-delete-action" type="button" disabled={saving} onClick={() => void onDelete()}>删除模型</button>
    </> : null}
    {page === "inputOutput" && model.model_type === "embedding" ? <>
    <div className="model-settings-block">
      <h3>{navigationLabels.inputModalities}</h3>
      <ModelInputModalityEditor supportsText={caps.supports_text} mimeTypes={caps.file_mime_types} providerMimeTypes={providerAttachmentMimeTypes} disabled={saving || savingOutput} onChange={saveCapabilities} />
    </div>
    <div className="model-settings-block">
      <h3>{navigationLabels.outputFormats}</h3>
      <GroupedList layout="fields" density="standard">
        {([['independent', '独立向量'], ['fusion', '融合向量']] as const).map(([key, label]) => <div className="field-row" key={key}>
          <span>{label}</span>
          <SelectPopover interactionOwner="row" disabled={saving || savingOutput} menuWidth="content" menuAlign="end" ariaLabel={label} value={caps[key]}
            options={Object.entries(statusLabels).map(([value, label]) => ({ value: value as EmbeddingCapabilities[typeof key], label }))}
            onChange={async value => {
              if (saving || savingOutput) return;
              setSavingOutput(true);
              try { await saveCapabilities({ [key]: value }); setError(""); }
              catch (cause) { setError(cause instanceof Error ? cause.message : "向量输出格式保存失败。"); }
              finally { setSavingOutput(false); }
            }} />
        </div>)}
        {input("embedding_dimensions", "输出维度")}
      </GroupedList>
      {error && <p role="alert">{error}</p>}
    </div>
    </> : null}
  </div></div>;
}
