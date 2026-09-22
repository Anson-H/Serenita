import type { ProviderSummary } from "../../../api/models/modelTypes";
import type { ProviderConnectionTestState } from "../../../utils/requestStatus";
import { GroupedList } from "../../../components/GroupedList";
import { EmptyState } from "../../../components/EmptyState";
import { CheckIcon, XIcon, LightningIcon } from "../../../components/icons";
import { navigationLabels } from "../../../components/navigationLabels";
import { SettingsListPanel, SettingsListForwardIcon } from "../../settings/SettingsPrimitives";
function renderProviderTestIcon(status: ProviderConnectionTestState["status"]) {
  if (status === "success") {
    return <CheckIcon />;
  }
  if (status === "error") {
    return <XIcon />;
  }
  return <LightningIcon />;
}

function providerConnectionStatusLabel(
  providerName: string,
  status: ProviderConnectionTestState["status"], configured: boolean
) {
  if (status === "testing") return `${providerName}：正在测试连接`;
  if (status === "success") return `${providerName}：连接成功`;
  if (status === "error") return `${providerName}：连接失败`;
  return `${providerName}：${configured ? "已配置" : "未配置"}`;
}

export function ProviderList({ providers, providerConnectionStates, selectedProviderId = "", detailOpen = false, selectProvider, onCreate }: {
  providers: ProviderSummary[]; providerConnectionStates: Record<string, ProviderConnectionTestState>; selectedProviderId?: string; detailOpen?: boolean;
  selectProvider: (id: string) => void; onCreate: () => void;
}) {
  return (
    <SettingsListPanel
      bodyClassName="provider-list"
      title={navigationLabels.providers}
      titleId="settings-provider-list-title"
    >
      {providers.length ? (
        <GroupedList className="provider-grouped-list" density="standard">
          {providers.map((provider) => {
            const connectionState = providerConnectionStates[provider.provider_id] ?? {
              status: "idle",
              message: ""
            };
            const active = detailOpen && provider.provider_id === selectedProviderId;
            return (
              <button
                aria-current={active ? "page" : undefined}
                aria-label={provider.provider_name}
                className="provider-row provider-option"
                data-interaction-owner="row"
                onClick={() => selectProvider(provider.provider_id)}
                type="button"
                data-active={active ? "true" : undefined}
                key={provider.provider_id}
              >
                <span className="provider-row-select">
                  <strong>{provider.provider_name}</strong>
                </span>
                <span className="provider-row-actions">
                  <span
                    aria-busy={connectionState.status === "testing"}
                    aria-label={providerConnectionStatusLabel(
                      provider.provider_name,
                      connectionState.status, provider.is_configured
                    )}
                    className={`provider-configured-icon provider-list-test-icon ${connectionState.status === "idle" ? provider.is_configured ? "success" : "unconfigured" : connectionState.status}`}
                    role="status"
                  >
                    {renderProviderTestIcon(connectionState.status === "idle" ? provider.is_configured ? "success" : "error" : connectionState.status)}
                  </span>
                  <SettingsListForwardIcon className="provider-row-chevron" />
                </span>
              </button>
            );
          })}
          <button type="button" className="control control--row grouped-list-create-button" onClick={onCreate}>添加自定义提供方</button>
        </GroupedList>
      ) : (
        <><EmptyState layout="inline" title="暂无模型提供方。" /><button type="button" className="control control--row" onClick={onCreate}>添加自定义提供方</button></>
      )}
    </SettingsListPanel>
  );
}
