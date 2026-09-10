import { useState } from "react";
import { ContentDialog } from "../../components/ContentDialog";
import { GroupedList } from "../../components/GroupedList";
import { CheckIcon, OtherFormatIcon, SlidersIcon, TextFormatIcon, XIcon } from "../../components/icons";
import { navigationLabels } from "../../components/navigationLabels";
import { isStandardMimeType, mimeTypeGroups } from "./ModelCapabilitySummary";
import { ModelChoiceRow } from "./ModelChoiceRow";
import { SettingsListForwardIcon } from "./SettingsPrimitives";

export function ModelInputModalityEditor({ supportsText, mimeTypes, providerMimeTypes = [], disabled = false, onChange }: {
  supportsText: boolean;
  mimeTypes: string[];
  providerMimeTypes?: string[];
  disabled?: boolean;
  onChange: (patch: { supports_text?: boolean; file_mime_types?: string[] }) => void | Promise<void>;
}) {
  const [customOpen, setCustomOpen] = useState(false);
  const [draft, setDraft] = useState("");
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  const other = mimeTypes.filter(mime => !isStandardMimeType(mime));
  function openCustom() { setDraft(mimeTypes.join("\n")); setError(""); setCustomOpen(true); }
  async function change(patch: Parameters<typeof onChange>[0], close = false) {
    setSaving(true);
    try { await onChange(patch); setError(""); if (close) setCustomOpen(false); }
    catch (cause) { setError(cause instanceof Error ? cause.message : "输入模态保存失败。"); }
    finally { setSaving(false); }
  }
  return <div className="model-format-block">
    <GroupedList className="model-capability-list model-input-options" selectionMode="multiple" density="standard">
      <ModelChoiceRow active={supportsText} disabled={disabled || saving} icon={<TextFormatIcon className="model-capability-option-icon" />} label="文本" onClick={() => void change({ supports_text: !supportsText })} />
      {mimeTypeGroups.map(group => {
        const formats = mimeTypes.filter(group.matches);
        const providerDefaults = providerMimeTypes.filter(group.matches);
        const defaults = providerDefaults.length ? providerDefaults : group.defaultMimeTypes;
        return <ModelChoiceRow key={group.key} active={formats.length > 0} disabled={disabled || saving} icon={group.icon} label={group.label} formatHint={formats.join("、") || undefined}
          onClick={() => void change({ file_mime_types: [...mimeTypes.filter(mime => !group.matches(mime)), ...(formats.length ? [] : defaults)] })} />;
      })}
      <ModelChoiceRow active={other.length > 0} disabled={disabled || saving} icon={<OtherFormatIcon className="model-capability-option-icon" />} label="其它" formatHint={other.join("、") || undefined}
        onClick={() => other.length ? void change({ file_mime_types: mimeTypes.filter(isStandardMimeType) }) : openCustom()} />
      <button className="model-capability-navigation-row model-detail-customize-button" disabled={disabled || saving} onClick={openCustom} type="button">
        <span className="model-capability-choice-copy"><SlidersIcon className="model-capability-option-icon" /><span>{navigationLabels.customFormat}</span></span>
        <SettingsListForwardIcon />
      </button>
    </GroupedList>
    {error && !customOpen ? <p role="alert">{error}</p> : null}
    {customOpen ? <ContentDialog title={navigationLabels.customFormat} onClose={() => setCustomOpen(false)} busy={saving} actions={<>
      <button className="control control--secondary" disabled={saving} type="button" onClick={() => setCustomOpen(false)}><XIcon /><span>取消</span></button>
      <button className="control control--primary" disabled={saving} type="button" onClick={() => void change({ file_mime_types: [...new Set(draft.split(/[\n,]/).map(mime => mime.trim()).filter(Boolean))] }, true)}><CheckIcon /><span>完成</span></button>
    </>}>
      <label className="model-format-modal-field"><span>MIME 类型</span><textarea aria-label="精确编辑 MIME 类型" autoFocus rows={8} placeholder="每行一个，例如 image/png" value={draft} onChange={event => setDraft(event.target.value)} disabled={saving} /></label>
      {error ? <p role="alert">{error}</p> : null}
    </ContentDialog> : null}
  </div>;
}
