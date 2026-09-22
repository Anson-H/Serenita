import { navigationLabels } from "../../../components/navigationLabels";
import { EmptyState } from "../../../components/EmptyState";
import { useEffect } from "react";
import { GroupedList } from "../../../components/GroupedList";
import {
  CheckIcon, LightningIcon, XIcon
} from "../../../components/icons";
import { SecretInput } from "../../../components/SecretInput";
import { SelectPopover } from "../../../components/SelectPopover";
import { useStatusNotification } from "../../../components/StatusNotificationCenter";
import { Switch } from "../../../components/Switch";
import { type ProviderConnectionTestState } from "../../../utils/requestStatus";

import { useWebSettings } from "./useWebSettings";
import { SettingsSectionLayout } from "../SettingsSectionLayout";
import { useSettingsNavigation, type SettingsSession } from "../SettingsNavigationContext";
function renderProviderTestIcon(status: ProviderConnectionTestState["status"]) {
  if (status === "success") {
    return <CheckIcon />;
  }
  if (status === "error") {
    return <XIcon />;
  }
  return <LightningIcon />;
}

function connectionTestActionLabel(status: ProviderConnectionTestState["status"]) {
  if (status === "testing") return "测试中";
  if (status === "success") return "测试成功";
  if (status === "error") return "测试失败";
  return "测试连接";
}

function providerConnectionTestButtonLabel(
  providerName: string,
  status: ProviderConnectionTestState["status"]
) {
  if (status === "success" || status === "error") {
    return `重新测试连接：${providerName}，当前${connectionTestActionLabel(status)}`;
  }
  return `${providerName}：${connectionTestActionLabel(status)}`;
}

export function WebSettingsSection({ session }: { session: SettingsSession }) {
  const { actions: { activeSection }, location } = useSettingsNavigation();
  const { webAccess, webApiUrls, webApiKeys, webFeedback, webProviderFeedback,
    webConnectionTestStates, updateWebApiUrl, saveWebApiUrl, updateWebApiKey,
    revealWebCredential, updateWebSettings, testWebProvider, loadError, resetConnectionTests } = useWebSettings(session);
  useEffect(() => { if (location.section === "web") resetConnectionTests(); }, [location]);
  const activeWebProvider = (webAccess?.providers ?? []).find(
    (provider) => provider.provider_id === webAccess?.active_provider_id
  ) ?? webAccess?.providers[0] ?? null;
  const activeWebProviderApiUrl = activeWebProvider
    ? webApiUrls[activeWebProvider.provider_id] ?? activeWebProvider.api_url
    : "";
  const activeWebProviderFeedback = activeWebProvider
    ? webProviderFeedback[activeWebProvider.provider_id]
    : undefined;
  const activeWebProviderConnectionState = activeWebProvider
    ? webConnectionTestStates[activeWebProvider.provider_id] ?? {
      status: "idle" as const,
      message: ""
    }
    : null;
  const activeWebProviderTestStatus = activeWebProviderConnectionState?.status ?? "idle";
  const activeWebProviderBusy = activeWebProviderFeedback?.status === "saving"
    || activeWebProviderTestStatus === "testing";
  const activeWebApiKey = activeWebProvider
    ? webApiKeys[activeWebProvider.provider_id] ?? ""
    : "";

  useStatusNotification(loadError, { id: "settings-web-load-error", title: "设置加载失败", tone: "error" });
  useStatusNotification(webFeedback.status === "error" ? webFeedback.message : "", { id: "settings-web-status", title: "联网工具设置未完成", tone: "error" });
  useStatusNotification(activeWebProviderFeedback?.status === "error" ? activeWebProviderFeedback.message : "", { id: "settings-web-provider-error", title: activeWebProvider ? `${activeWebProvider.provider_name} 操作未完成` : "联网服务操作未完成", tone: "error" });
  if (activeSection !== "web") return null;
  return <SettingsSectionLayout title={navigationLabels.web} wide><div className="settings-detail-column">
    <section className="settings-section web-access-section">
      <GroupedList layout="fields" className="web-access-controls" density="standard">
        <div className="web-access-toggle-row field-row">
          <strong>启用联网工具</strong>
          <Switch
            checked={webAccess?.is_enabled ?? false}
            disabled={!webAccess || webFeedback.status === "saving" || activeWebProviderBusy}
            label="启用联网工具"
            onChange={(isEnabled) => void updateWebSettings({ is_enabled: isEnabled })}
          />
        </div>

        <div className="web-provider-picker-row field-row">
          <strong>当前服务</strong>
          <SelectPopover
            ariaLabel="选择联网工具服务"
            disabled={!webAccess || webFeedback.status === "saving" || activeWebProviderBusy}
            menuWidth="content" menuAlign="end" interactionOwner="row"
            onChange={(providerId) => void updateWebSettings({
              active_provider_id: providerId as "tavily" | "exa"
            })}
            options={(webAccess?.providers ?? []).map((provider) => ({
              label: provider.provider_name,
              value: provider.provider_id
            }))}
            value={activeWebProvider?.provider_id ?? "tavily"}
          />
        </div>
      </GroupedList>

      {activeWebProvider ? (
        <form
          aria-label={`${activeWebProvider.provider_name} 联网配置`}
          className="provider-form web-provider-form"
          onSubmit={(event) => event.preventDefault()}
        >
          <h2 className="web-provider-name">{activeWebProvider.provider_name}</h2>
          <GroupedList layout="fields" className="api-credential-fields" density="standard">
            <label className="field-row" htmlFor={`web-api-url-${activeWebProvider.provider_id}`}>
              API 地址
              <input
                autoComplete="url"
                disabled={activeWebProviderTestStatus === "testing"}
                id={`web-api-url-${activeWebProvider.provider_id}`}
                inputMode="url"
                onBlur={() => void saveWebApiUrl(activeWebProvider.provider_id)}
                onChange={(event) => updateWebApiUrl(
                  activeWebProvider.provider_id,
                  event.target.value
                )}
                spellCheck={false}
                value={activeWebProviderApiUrl}
              />
            </label>
            <div className="secret-field field-row">
              <label htmlFor={`web-api-key-${activeWebProvider.provider_id}`}>API key</label>
              <SecretInput
                autoComplete="off"
                disabled={activeWebProviderTestStatus === "testing"}
                id={`web-api-key-${activeWebProvider.provider_id}`}
                labelForAction={`${activeWebProvider.provider_name} API key`}
                onReveal={() => revealWebCredential(activeWebProvider.provider_id)}
                hasSavedValue={activeWebProvider.has_api_key}
                placeholder="输入 API key"
                spellCheck={false}
                value={activeWebApiKey}
                onChange={(event) => updateWebApiKey(activeWebProvider.provider_id, event.target.value)}
              />
            </div>
            <button
              aria-busy={activeWebProviderTestStatus === "testing"}
              aria-label={providerConnectionTestButtonLabel(
                activeWebProvider.provider_name,
                activeWebProviderTestStatus
              )}
              className={`control control--secondary secondary-button control-primary provider-connection-test-action web-provider-test-button ${activeWebProviderTestStatus}`}
              disabled={activeWebProviderTestStatus !== "testing" && (activeWebProviderBusy
                || (!activeWebApiKey.trim() && !activeWebProvider.has_api_key))}
              onClick={() => void testWebProvider(activeWebProvider.provider_id)}
              type="button"
            >
              {renderProviderTestIcon(activeWebProviderTestStatus)}
              <span>{connectionTestActionLabel(activeWebProviderTestStatus)}</span>
            </button>
          </GroupedList>
        </form>
      ) : (
        <EmptyState layout="inline" title="暂无可用联网服务。" />
      )}
    </section>
  </div></SettingsSectionLayout>;
}
