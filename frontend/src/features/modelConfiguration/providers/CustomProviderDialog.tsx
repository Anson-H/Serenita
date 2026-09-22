import { useId, useState, type FormEvent } from "react";
import { useModelSettingsApi } from "../ModelSettingsApi";
import type { ProviderSummary } from "../../../api/models/modelTypes";
import { modelConfigurationChanged } from "../../../api/models/modelServiceApi";
import { ContentDialog } from "../../../components/ContentDialog";
import { GroupedList } from "../../../components/GroupedList";
import { SecretInput } from "../../../components/SecretInput";
import { CheckIcon } from "../../../components/icons";

export function CustomProviderDialog({ provider, onClose, onSaved }: { provider?: ProviderSummary; onClose: () => void; onSaved: (id: string) => void }) {
  const api = useModelSettingsApi();
  const [name, setName] = useState(provider?.provider_name ?? "");
  const [url, setUrl] = useState(provider?.api_url ?? "");
  const [official, setOfficial] = useState(provider?.official_url ?? "");
  const [key, setKey] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const formId = useId();
  async function save(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError("");
    try {
      const result = await api.saveCustomProvider(provider?.provider_id, { provider_name: name, api_url: url, official_url: official, ...(key ? { api_key: key } : {}) });
      modelConfigurationChanged(); onSaved(result.provider_id); onClose();
    } catch (cause) { setError(cause instanceof Error ? cause.message : "保存失败。"); }
    finally { setBusy(false); }
  }
  return <ContentDialog title={provider ? "编辑提供方名称" : "添加自定义提供方"} onClose={onClose} creation busy={busy} bodyClassName="settings-section" actions={
    <button className="control control--primary" type="submit" form={formId} disabled={busy}><CheckIcon /><span>{busy ? "保存中…" : "完成"}</span></button>
  }>
    <p className="content-description">支持兼容的对话与向量接口。无鉴权服务可留空 API Key。</p>
    <form id={formId} onSubmit={save}>
      <GroupedList density="standard" layout="fields">
        <label className="field-row"><span>提供方名称</span><input disabled={busy} required maxLength={50} value={name} onChange={e => setName(e.target.value)} /></label>
        {!provider ? <><label className="field-row"><span>API 基础地址</span><input disabled={busy} required type="url" value={url} onChange={e => setUrl(e.target.value)} placeholder="https://example.com/v1" /></label>
          <label className="field-row"><span>API Key</span><SecretInput disabled={busy} labelForAction="API Key" autoComplete="off" value={key} onChange={e => setKey(e.target.value)} placeholder="可留空" /></label>
          <label className="field-row"><span>官方网站（可选）</span><input disabled={busy} type="url" value={official} onChange={e => setOfficial(e.target.value)} /></label></> : null}
      </GroupedList>
    </form>
    {error ? <p className="content-description" role="alert">{error}</p> : null}
  </ContentDialog>;
}
