import { useState, type FormEvent, type ReactNode } from "react";

import type { AddedModel, ProviderSummary, RemoteModel } from "../../api/client";
import {
  CheckIcon,
  ChevronRightIcon,
  LightningIcon,
  SidebarBackIcon,
  TrashIcon,
  XIcon
} from "../../components/icons";
import { SecretInput } from "../../components/SecretInput";
import type {
  AccountPanel,
  DefaultModelUsage,
  ProviderConnectionTestState,
  ProviderDraft,
  SettingsMobileLayer,
  SettingsSection,
  TestState
} from "./settingsTypes";

type DefaultModelItem = {
  key: DefaultModelUsage;
  label: string;
  selectedModelId: string;
};

type SettingsViewProps = {
  account: string;
  accountFeedback: TestState;
  accountPanel: AccountPanel;
  activeSection: SettingsSection;
  addedModels: AddedModel[];
  changePassword: (event: FormEvent<HTMLFormElement>) => void;
  confirmPassword: string;
  currentPassword: string;
  deleteAddedModel: (modelId: string) => void | Promise<void>;
  defaultModelItems: DefaultModelItem[];
  defaultModelOptions: AddedModel[];
  goBackSettingsLayer: () => void;
  loadError: string;
  mobileLayer: SettingsMobileLayer;
  mobileSidebarToggle?: ReactNode;
  modelPickerError: string;
  modelPickerLoading: boolean;
  modelPickerOpen: boolean;
  nameDraft: string;
  newPassword: string;
  openAddModelModal: () => void | Promise<void>;
  onSignOut: () => void;
  providerConnectionStates: Record<string, ProviderConnectionTestState>;
  providers: ProviderSummary[];
  remoteModels: RemoteModel[];
  addRemoteModel: (model: RemoteModel) => void | Promise<void>;
  selectedDraft?: ProviderDraft;
  selectedProvider?: ProviderSummary;
  selectedProviderFeedback?: TestState;
  selectedProviderId: string;
  selectedProviderModels: AddedModel[];
  selectAccountPanel: (panel: AccountPanel) => void;
  selectDefaultsRoot: () => void;
  selectProvider: (providerId: string) => void;
  selectProvidersRoot: () => void;
  setConfirmPassword: (value: string) => void;
  setCurrentPassword: (value: string) => void;
  setModelPickerOpen: (open: boolean) => void;
  setNameDraft: (value: string) => void;
  setNewPassword: (value: string) => void;
  retryLoadRemoteModels: () => void | Promise<void>;
  settingsMobileLayerTitle: () => string;
  testProviderConnection: (providerId: string, options?: { notify?: boolean }) => void | Promise<void>;
  updateDefaultModel: (usage: DefaultModelUsage, modelId: string) => void | Promise<void>;
  updateDraft: (providerId: string, patch: Partial<ProviderDraft>) => void;
};

function PlusIcon() {
  return (
    <svg aria-hidden="true" className="settings-action-icon" fill="none" viewBox="0 0 24 24">
      <path
        d="M12 5v14M5 12h14"
        stroke="currentColor"
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth="2.4"
      />
    </svg>
  );
}

function renderProviderTestIcon(status: ProviderConnectionTestState["status"]) {
  if (status === "success") {
    return <CheckIcon />;
  }
  if (status === "error") {
    return <XIcon />;
  }
  return <LightningIcon />;
}

export function SettingsView({
  account,
  accountFeedback,
  accountPanel,
  activeSection,
  addedModels,
  changePassword,
  confirmPassword,
  currentPassword,
  deleteAddedModel,
  defaultModelItems,
  defaultModelOptions,
  goBackSettingsLayer,
  loadError,
  mobileLayer,
  mobileSidebarToggle,
  modelPickerError,
  modelPickerLoading,
  modelPickerOpen,
  nameDraft,
  newPassword,
  openAddModelModal,
  onSignOut,
  providerConnectionStates,
  providers,
  remoteModels,
  addRemoteModel,
  selectedDraft,
  selectedProvider,
  selectedProviderFeedback,
  selectedProviderId,
  selectedProviderModels,
  selectAccountPanel,
  selectDefaultsRoot,
  selectProvider,
  selectProvidersRoot,
  setConfirmPassword,
  setCurrentPassword,
  setModelPickerOpen,
  setNameDraft,
  setNewPassword,
  retryLoadRemoteModels,
  settingsMobileLayerTitle,
  testProviderConnection,
  updateDefaultModel,
  updateDraft
}: SettingsViewProps) {
  const [openDefaultModelPicker, setOpenDefaultModelPicker] = useState<DefaultModelUsage | null>(null);

  function defaultModelOptionsForUsage(usage: DefaultModelUsage) {
    if (usage !== "vision_parse") {
      return defaultModelOptions;
    }
    return defaultModelOptions.filter((model) =>
      model.file_mime_types.some((mimeType) => mimeType.startsWith("image/"))
    );
  }

  function currentDefaultModelName(item: DefaultModelItem) {
    return (
      defaultModelOptions.find((model) => model.model_id === item.selectedModelId)?.model_name ?? "不设置"
    );
  }

  function toggleDefaultModelPicker(usage: DefaultModelUsage) {
    setOpenDefaultModelPicker((current) => (current === usage ? null : usage));
  }

  function chooseDefaultModel(usage: DefaultModelUsage, modelId: string) {
    setOpenDefaultModelPicker(null);
    void updateDefaultModel(usage, modelId);
  }

  return (
    <>
      <section
        className="settings-shell settings-three-column"
        aria-label="账号设置"
        data-active-section={activeSection}
        data-mobile-layer={mobileLayer}
      >
        <div className="settings-mobile-layer-header">
          {mobileLayer === "root" ? (
            mobileSidebarToggle ?? <span aria-hidden="true" />
          ) : (
            <button
              aria-label="返回上一级"
              className="settings-mobile-back-button"
              onClick={goBackSettingsLayer}
              type="button"
            >
              <SidebarBackIcon />
            </button>
          )}
          <strong>{settingsMobileLayerTitle()}</strong>
          <span aria-hidden="true" />
        </div>
        <aside className="settings-nav settings-primary-nav" aria-label="设置导航">
          <div className="settings-root-list">
            <button
              className={
                activeSection === "account" && accountPanel === "profile"
                  ? "settings-nav-item active"
                  : "settings-nav-item"
              }
              onClick={() => selectAccountPanel("profile")}
              type="button"
            >
              <span>账号资料</span>
              <span className="settings-nav-chevron" aria-hidden="true">
                <ChevronRightIcon />
              </span>
            </button>
            <button
              className={
                activeSection === "account" && accountPanel === "password"
                  ? "settings-nav-item active"
                  : "settings-nav-item"
              }
              onClick={() => selectAccountPanel("password")}
              type="button"
            >
              <span>密码安全</span>
              <span className="settings-nav-chevron" aria-hidden="true">
                <ChevronRightIcon />
              </span>
            </button>
            <button
              className={activeSection === "providers" ? "settings-nav-item active" : "settings-nav-item"}
              onClick={selectProvidersRoot}
              type="button"
            >
              <span>模型提供方</span>
              <span className="settings-nav-chevron" aria-hidden="true">
                <ChevronRightIcon />
              </span>
            </button>
            <button
              className={activeSection === "defaults" ? "settings-nav-item active" : "settings-nav-item"}
              onClick={selectDefaultsRoot}
              type="button"
            >
              <span>默认模型</span>
              <span className="settings-nav-chevron" aria-hidden="true">
                <ChevronRightIcon />
              </span>
            </button>
            <button
              className="settings-nav-item settings-sign-out-button danger"
              onClick={onSignOut}
              type="button"
            >
              <span>退出登录</span>
            </button>
          </div>
        </aside>

        {activeSection === "providers" ? (
          <aside className="settings-list-column" aria-label="模型提供方列表">
            {loadError ? <p className="status-message error">{loadError}</p> : null}
            <div className="provider-list">
              {providers.map((provider) => {
                const connectionState = providerConnectionStates[provider.provider_id] ?? {
                  status: "idle",
                  message: ""
                };
                return (
                  <div
                    className={`provider-row provider-option ${
                      provider.provider_id === selectedProviderId ? "selected" : ""
                    }`}
                    key={provider.provider_id}
                  >
                    <button
                      className="provider-row-select"
                      onClick={() => selectProvider(provider.provider_id)}
                      type="button"
                    >
                      <div>
                        <strong>{provider.provider_name}</strong>
                      </div>
                    </button>
                    <span className="provider-row-actions">
                      <button
                        aria-label={`测试连接：${provider.provider_name}`}
                        className={`status provider-configured-icon provider-list-test-icon ${connectionState.status}`}
                        data-tooltip={connectionState.message || "测试连接"}
                        disabled={connectionState.status === "testing"}
                        onClick={(event) => {
                          event.stopPropagation();
                          void testProviderConnection(provider.provider_id, { notify: true });
                        }}
                        type="button"
                      >
                        {renderProviderTestIcon(connectionState.status)}
                      </button>
                      <span className="settings-nav-chevron provider-row-chevron" aria-hidden="true">
                        <ChevronRightIcon />
                      </span>
                    </span>
                  </div>
                );
              })}
              {!providers.length ? (
                <p className="status-message">暂无模型提供方。</p>
              ) : null}
            </div>
          </aside>
        ) : null}

        <main className="settings-detail-column">
          {activeSection === "account" && accountPanel === "profile" ? (
            <section className="settings-section">
              <h1>账号资料</h1>
              <div className="form-grid account-profile-grid">
                <label>
                  账号标识
                  <input value={account} readOnly />
                </label>
                <label>
                  用户名称
                  <input value={nameDraft} onChange={(event) => setNameDraft(event.target.value)} />
                </label>
              </div>
              {accountFeedback.message ? (
                <p className={`status-message account-feedback ${accountFeedback.status}`}>
                  {accountFeedback.message}
                </p>
              ) : null}
            </section>
          ) : null}

          {activeSection === "account" && accountPanel === "password" ? (
            <form className="settings-section password-section" onSubmit={changePassword}>
              <h1>修改密码</h1>
              <div className="form-grid password-grid">
                <div className="secret-field">
                  <label htmlFor="settings-current-password">当前密码</label>
                  <SecretInput
                    autoComplete="current-password"
                    id="settings-current-password"
                    labelForAction="当前密码"
                    value={currentPassword}
                    onChange={(event) => setCurrentPassword(event.target.value)}
                  />
                </div>
                <div className="secret-field">
                  <label htmlFor="settings-new-password">新密码</label>
                  <SecretInput
                    autoComplete="new-password"
                    id="settings-new-password"
                    labelForAction="新密码"
                    value={newPassword}
                    onChange={(event) => setNewPassword(event.target.value)}
                  />
                </div>
                <div className="secret-field">
                  <label htmlFor="settings-confirm-password">确认新密码</label>
                  <SecretInput
                    autoComplete="new-password"
                    id="settings-confirm-password"
                    labelForAction="确认新密码"
                    value={confirmPassword}
                    onChange={(event) => setConfirmPassword(event.target.value)}
                  />
                </div>
              </div>
              <button className="command-button" type="submit">
                更新密码
              </button>
              {accountFeedback.message ? (
                <p className={`status-message account-feedback ${accountFeedback.status}`}>
                  {accountFeedback.message}
                </p>
              ) : null}
            </form>
          ) : null}

          {activeSection === "providers" ? (
            <section className="settings-section provider-panel">
              <div className="provider-workspace">
                {selectedProvider && selectedDraft ? (
                  <form
                    className="provider-form"
                    onSubmit={(event) => {
                      event.preventDefault();
                    }}
                  >
                    <div className="form-grid provider-fields">
                      <label>
                        官网地址
                        <input
                          value={selectedDraft.officialUrl}
                          onChange={(event) =>
                            updateDraft(selectedProvider.provider_id, {
                              officialUrl: event.target.value
                            })
                          }
                        />
                      </label>
                      <label>
                        API 地址
                        <input
                          value={selectedDraft.baseUrl}
                          onChange={(event) =>
                            updateDraft(selectedProvider.provider_id, {
                              baseUrl: event.target.value
                            })
                          }
                        />
                      </label>
                      <div className="secret-field">
                        <label htmlFor="provider-api-key">API key</label>
                        <SecretInput
                          autoComplete="off"
                          id="provider-api-key"
                          labelForAction="API key"
                          spellCheck={false}
                          value={selectedDraft.apiKey}
                          onChange={(event) =>
                            updateDraft(selectedProvider.provider_id, {
                              apiKey: event.target.value
                            })
                          }
                        />
                      </div>
                    </div>
	                  </form>
	                ) : null}
	                {selectedProviderFeedback?.message ? (
	                  <p className={`status-message provider-feedback ${selectedProviderFeedback.status}`}>
	                    {selectedProviderFeedback.message}
	                  </p>
	                ) : null}

	                <section className="provider-model-section" aria-label="模型列表">
                  <div className="model-section-header">
                    <div className="model-section-title">
                      <h2>已添加模型</h2>
                      <span className="status">{selectedProviderModels.length} 个模型</span>
                      <button
                        aria-label="添加模型"
                        className="secondary-button settings-icon-button add-model-button"
                        onClick={() => void openAddModelModal()}
                        title="添加模型"
                        type="button"
                      >
                        <PlusIcon />
                      </button>
                    </div>
                  </div>
                  {selectedProviderModels.length ? (
                    <div className="model-list">
                      {selectedProviderModels.map((model) => (
                        <div className="model-row" key={model.model_id}>
                          <span>{model.model_name}</span>
                          <div className="model-row-actions">
                            <button
                              aria-label={`删除模型：${model.model_name}`}
                              className="settings-icon-button model-delete-button danger"
                              onClick={() => void deleteAddedModel(model.model_id)}
                              title="删除模型"
                              type="button"
                            >
                              <TrashIcon className="settings-action-icon" />
                            </button>
                          </div>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <p className="status-message">暂无模型。</p>
                  )}
                </section>
              </div>
            </section>
          ) : null}

          {activeSection === "defaults" ? (
            <section className="settings-section default-model-section">
              <h1>默认模型</h1>
              {defaultModelOptions.length ? (
                <div className="default-model-list">
                  {defaultModelItems.map((item) => (
                    <div className="default-model-row" key={item.key}>
                      <div className="default-model-copy">
                        <strong>{item.label}</strong>
                      </div>
                      <div className="default-model-picker">
                        <button
                          aria-expanded={openDefaultModelPicker === item.key}
                          aria-haspopup="listbox"
                          aria-label={`设置${item.label}`}
                          className="default-model-trigger"
                          onClick={() => toggleDefaultModelPicker(item.key)}
                          type="button"
                        >
                          <span>{currentDefaultModelName(item)}</span>
                          <span aria-hidden="true">⌄</span>
                        </button>
                        {openDefaultModelPicker === item.key ? (
                          <div
                            aria-label={`${item.label}候选模型`}
                            className="default-model-popover"
                            role="listbox"
                          >
                            <button
                              aria-selected={!item.selectedModelId}
                              className={!item.selectedModelId ? "default-model-option active" : "default-model-option"}
                              onClick={() => chooseDefaultModel(item.key, "")}
                              role="option"
                              type="button"
                            >
                              <span>不设置</span>
                              {!item.selectedModelId ? <span aria-hidden="true">✓</span> : null}
                            </button>
                            {defaultModelOptionsForUsage(item.key).map((model) => {
                              const selected = model.model_id === item.selectedModelId;
                              return (
                                <button
                                  aria-selected={selected}
                                  className={selected ? "default-model-option active" : "default-model-option"}
                                  key={model.model_id}
                                  onClick={() => chooseDefaultModel(item.key, model.model_id)}
                                  role="option"
                                  type="button"
                                >
                                  <span>{model.model_name}</span>
                                  {selected ? <span aria-hidden="true">✓</span> : null}
                                </button>
                              );
                            })}
                          </div>
                        ) : null}
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="status-message">请先添加模型。</p>
              )}
            </section>
          ) : null}
        </main>
      </section>
      {modelPickerOpen ? (
        <div className="model-picker-backdrop">
          <section className="model-picker-modal" role="dialog" aria-modal="true" aria-label="添加模型">
            <div className="model-picker-header">
              <div>
                <h2>添加模型</h2>
              </div>
              <button
                aria-label="关闭添加模型"
                className="secondary-button settings-icon-button"
                onClick={() => setModelPickerOpen(false)}
                title="关闭添加模型"
                type="button"
              >
                <XIcon />
              </button>
	            </div>
	            {modelPickerLoading ? <p className="status-message testing">加载中...</p> : null}
	            {!modelPickerLoading && modelPickerError ? (
	              <div className="model-picker-error-actions">
	                <p className="status-message error">{modelPickerError}</p>
	                <button className="secondary-button" onClick={() => void retryLoadRemoteModels()} type="button">
	                  重试
	                </button>
	              </div>
	            ) : null}
	            {!modelPickerLoading && !modelPickerError && remoteModels.length ? (
	              <div className="model-list">
                {remoteModels.map((model) => {
                  const added = addedModels.find(
                    (item) =>
                      item.provider_id === selectedProviderId &&
                      item.remote_model_id === model.remote_model_id
                  );
                  return (
                    <div className={added ? "model-row selected" : "model-row"} key={model.remote_model_id}>
                      <span>{model.model_name}</span>
                      <button
                        className="text-button"
                        disabled={Boolean(added)}
                        onClick={() => void addRemoteModel(model)}
                        type="button"
                      >
                        {added ? "已添加" : "添加"}
                      </button>
                    </div>
                  );
                })}
              </div>
            ) : null}
	            {!modelPickerLoading && !modelPickerError && !remoteModels.length ? (
	              <p className="status-message">暂无可添加模型。</p>
	            ) : null}
          </section>
        </div>
      ) : null}
    </>
  );
}
