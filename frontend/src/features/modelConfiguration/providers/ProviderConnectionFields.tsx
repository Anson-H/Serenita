import { GroupedList, ReadonlyField } from "../../../components/GroupedList";
import { SecretInput } from "../../../components/SecretInput";

/** Shared connection fields for account providers and official upstream providers. */
export function ProviderConnectionFields({ officialUrl, apiUrl, apiKey, hasApiKey, onApiUrlChange, onApiKeyChange,
  onOfficialUrlChange, onReveal, disabled = false, apiUrlDisabled = false, keyId = "provider-api-key" }: {
    officialUrl?: string; apiUrl: string; apiKey: string; hasApiKey: boolean;
    onApiUrlChange: (value: string) => void; onApiKeyChange: (value: string) => void;
    onOfficialUrlChange?: (value: string) => void; onReveal?: () => boolean | Promise<boolean>;
    disabled?: boolean; apiUrlDisabled?: boolean; keyId?: string;
  }) {
  return <>
    {officialUrl !== undefined ? <GroupedList layout="fields" density="standard">
      {onOfficialUrlChange ? <label className="field-row">官网地址<input disabled={disabled} value={officialUrl} onChange={event => onOfficialUrlChange(event.target.value)} /></label>
        : <ReadonlyField label="官网地址" value={officialUrl || "未设置"} />}
    </GroupedList> : null}
    <GroupedList layout="fields" className="api-credential-fields" density="standard">
      <label className="field-row">API 地址<input disabled={disabled || apiUrlDisabled} value={apiUrl} onChange={event => onApiUrlChange(event.target.value)} /></label>
      <div className="secret-field field-row"><label htmlFor={keyId}>API key</label>
        <SecretInput autoComplete="off" id={keyId} labelForAction="API key" disabled={disabled} onReveal={onReveal}
          hasSavedValue={hasApiKey} placeholder="输入 API key" spellCheck={false} value={apiKey} onChange={event => onApiKeyChange(event.target.value)} />
      </div>
    </GroupedList>
  </>;
}
