import { useEffect, useMemo, useRef, useState, type FormEvent, type ReactNode } from "react";
import { createPortal } from "react-dom";
import type {
  AddedModel,
  ModelUpdatePayload,
  ProviderSummary,
  RemoteModel,
  WebAccessSettings
} from "../../api/client";
import { GroupedList } from "../../components/GroupedList";
import {
  CheckIcon,
  ChevronLeftIcon,
  LightningIcon,
  LockIcon,
  PlusIcon,
  XIcon
} from "../../components/icons";
import { SecretInput } from "../../components/SecretInput";
import { SelectPopover } from "../../components/SelectPopover";
import { useStatusNotification, type StatusNotificationTone } from "../../components/StatusNotificationCenter";
import { Switch } from "../../components/Switch";
import { useModalDialog } from "../../components/useModalDialog";
import { WorkspaceToolbar } from "../../components/WorkspaceToolbar";
import { keepTextControlFocused, syncCommittedText } from "../../utils/inputMethod";
import type { ComposerSubmitShortcut } from "../accountPreferences/composerSubmitShortcut";
import type {
  BaseContextAssemblyDisplayMode,
  BaseContextAssemblyType
} from "../accountPreferences/contextAssemblyDisplay";
import type { ToolExecutionDisplayType } from "../accountPreferences/toolExecutionDisplay";
import { MemberGrantsPanel, MembersPanel } from "../members/MemberSettings";
import {
  ConversationSettingsDetail,
  ConversationSettingsList,
  conversationSettingsSections
} from "./ConversationSettingsPanel";
import type { LabDictionaryDetailPage } from "./labDictionaryDrafts";
import {
  LabDictionaryEditor
} from "./LabDictionaryEditor";
import type { ModelSettingsPage } from "./ModelSettingsEditor";
import { ModelSettingsEditor } from "./ModelSettingsEditor";
import { RemoteModelPicker } from './RemoteModelPicker';
import { groupRemoteModelsBySupplier } from "./remoteModelPresentation";
import { SettingsDetailPanel } from "./SettingsDetailPanel";
import {
  SettingsNavigation,
  type SettingsNavigationTarget
} from "./SettingsNavigation";
import { SettingsListForwardIcon, SettingsListPanel } from "./SettingsPrimitives";
import {
  type AccountPanel,
  type ConversationSettingsSection,
  type DefaultModelUsage,
  type LabCatalog,
  type ProviderConnectionTestState,
  type ProviderDraft,
  type SettingsMobileLayer,
  type SettingsSection,
  type TestState
} from "./settingsTypes";

type DefaultModelItem = {
  key: DefaultModelUsage;
  label: string;
  selectedModelId: string;
};

type SettingsViewProps = {
  accountDraft: string;
  accountFeedback: TestState;
  accountPanel: AccountPanel;
  activeSection: SettingsSection;
  addedModels: AddedModel[];
  addingRemoteModelIds: string[];
  changePassword: (event: FormEvent<HTMLFormElement>) => void;
  confirmPassword: string;
  conversationSection: ConversationSettingsSection;
  composerSubmitShortcut: ComposerSubmitShortcut;
  baseContextDisplayModes: Record<BaseContextAssemblyType, BaseContextAssemblyDisplayMode>;
  contextDisplayTypes: string[];
  showContextWindowUsage: boolean;
  showRelatedContent: boolean;
  showTokenUsage: boolean;
  toolDisplayTypes: ToolExecutionDisplayType[];
  currentPassword: string;
  deleteAddedModel: (modelId: string) => boolean | Promise<boolean>;
  defaultModelItems: DefaultModelItem[];
  defaultModelOptions: AddedModel[];
  detailOpen: boolean;
  closeSettingsDetail: () => void;
  goBackSettingsLayer: () => void;
  loadError: string;
  mobileLayer: SettingsMobileLayer;
  mobileSidebarToggle?: ReactNode;
  modelPickerError: string;
  modelPickerLoading: boolean;
  modelPickerOpen: boolean;
  probingModelIds: string[];
  probeAddedModel: (modelId: string) => void | Promise<void>;
  nameDraft: string;
  newPassword: string;
  openAddModelModal: () => void | Promise<void>;
  onReportsChanged: () => void;
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
  selectConversationRoot: () => void;
  selectConversationSection: (section: ConversationSettingsSection) => void;
  selectDefaultsRoot: () => void;
  selectLabCatalogRoot: (catalog: LabCatalog) => void;
  openSettingsDetail: () => void;
  selectProvider: (providerId: string) => void;
  selectProvidersRoot: () => void;
  setConfirmPassword: (value: string) => void;
  setCurrentPassword: (value: string) => void;
  setAccountDraft: (value: string) => void;
  setModelPickerOpen: (open: boolean) => void;
  setNameDraft: (value: string) => void;
  setNewPassword: (value: string) => void;
  retryLoadRemoteModels: () => void | Promise<void>;
  revealModelCredential: (providerId: string) => boolean | Promise<boolean>;
  revealWebCredential: (providerId: string) => boolean | Promise<boolean>;
  settingsMobileLayerTitle: () => string;
  testProviderConnection: (providerId: string, options?: { notify?: boolean }) => void | Promise<void>;
  savingModelIds: string[];
  updateAddedModel: (
    modelId: string,
    patch: ModelUpdatePayload,
    options?: { notify?: boolean }
  ) => void | Promise<void>;
  updateDefaultModel: (usage: DefaultModelUsage, modelId: string) => void | Promise<void>;
  updateBaseContextDisplayMode: (
    contextType: BaseContextAssemblyType,
    mode: BaseContextAssemblyDisplayMode
  ) => void;
  updateComposerSubmitShortcut: (shortcut: ComposerSubmitShortcut) => void;
  updateContextDisplayType: (contextType: string, visible: boolean) => void;
  updateShowRelatedContent: (visible: boolean) => void;
  updateShowContextWindowUsage: (visible: boolean) => void;
  updateShowTokenUsage: (visible: boolean) => void;
  updateToolDisplayType: (type: ToolExecutionDisplayType, visible: boolean) => void;
  updateDraft: (providerId: string, patch: Partial<ProviderDraft>) => void;
  selectWebRoot: () => void;
  selectMembersRoot: () => void;
  webAccess: WebAccessSettings | null;
  webApiUrls: Record<string, string>;
  webApiKeys: Record<string, string>;
  webFeedback: TestState;
  webConnectionTestStates: Record<string, ProviderConnectionTestState>;
  webProviderFeedback: Record<string, TestState>;
  saveWebApiUrl: (providerId: string) => boolean | Promise<boolean>;
  updateWebApiUrl: (providerId: string, value: string) => void;
  updateWebApiKey: (providerId: string, value: string) => void;
  updateWebSettings: (patch: {
    is_enabled?: boolean;
    active_provider_id?: "tavily" | "exa";
  }) => void | Promise<void>;
  testWebProvider: (providerId: string) => void | Promise<void>;
};

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
  status: ProviderConnectionTestState["status"]
) {
  if (status === "testing") return `${providerName}：正在测试连接`;
  if (status === "success") return `${providerName}：连接成功`;
  if (status === "error") return `${providerName}：连接失败`;
  return `${providerName}：等待连接测试`;
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

const modelSettingsPageTitles: Record<Exclude<ModelSettingsPage, "root">, string> = {
  thinking: "思考档位",
  format: "输入与输出"
};

export function SettingsView({
  accountDraft,
  accountFeedback,
  accountPanel,
  activeSection,
  addedModels,
  addingRemoteModelIds,
  baseContextDisplayModes,
  changePassword,
  confirmPassword,
  conversationSection,
  composerSubmitShortcut,
  contextDisplayTypes,
  showContextWindowUsage,
  showRelatedContent,
  showTokenUsage,
  toolDisplayTypes,
  currentPassword,
  deleteAddedModel,
  defaultModelItems,
  defaultModelOptions,
  detailOpen,
  closeSettingsDetail,
  goBackSettingsLayer,
  loadError,
  mobileLayer,
  mobileSidebarToggle,
  modelPickerError,
  modelPickerLoading,
  modelPickerOpen,
  probingModelIds,
  probeAddedModel,
  nameDraft,
  newPassword,
  openAddModelModal,
  onReportsChanged,
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
  selectConversationRoot,
  selectConversationSection,
  selectDefaultsRoot,
  selectLabCatalogRoot,
  openSettingsDetail,
  selectProvider,
  selectProvidersRoot,
  setConfirmPassword,
  setCurrentPassword,
  setAccountDraft,
  setModelPickerOpen,
  setNameDraft,
  setNewPassword,
  retryLoadRemoteModels,
  revealModelCredential,
  revealWebCredential,
  settingsMobileLayerTitle,
  savingModelIds,
  testProviderConnection,
  updateDefaultModel,
  updateBaseContextDisplayMode,
  updateComposerSubmitShortcut,
  updateContextDisplayType,
  updateShowRelatedContent,
  updateShowContextWindowUsage,
  updateShowTokenUsage,
  updateToolDisplayType,
  updateDraft,
  updateAddedModel,
  selectWebRoot,
  selectMembersRoot,
  webAccess,
  webApiUrls,
  webApiKeys,
  webFeedback,
  webConnectionTestStates,
  webProviderFeedback,
  saveWebApiUrl,
  updateWebApiUrl,
  updateWebApiKey,
  updateWebSettings,
  testWebProvider
}: SettingsViewProps) {
  const [editingModelId, setEditingModelId] = useState("");
  const [editingModelPage, setEditingModelPage] = useState<ModelSettingsPage>("root");
  const [labDictionaryDetailPage, setLabDictionaryDetailPage] = useState<LabDictionaryDetailPage>("root");
  const [labDictionaryDetailTitle, setLabDictionaryDetailTitle] = useState("");
  const [modelPickerQuery, setModelPickerQuery] = useState("");
  const [removingModelIds, setRemovingModelIds] = useState<string[]>([]);
  const settingsShellRef = useRef<HTMLElement | null>(null);
  const settingsReturnFocusRef = useRef<HTMLElement | null>(null);
  const modelPickerDialogRef = useRef<HTMLElement | null>(null);
  const previousDetailOpenRef = useRef(detailOpen);
  const [expandedModelSupplierGroups, setExpandedModelSupplierGroups] = useState<Set<string>>(
    () => new Set()
  );
  const [expandedSearchModelSupplierGroups, setExpandedSearchModelSupplierGroups] = useState<Set<string>>(
    () => new Set()
  );
  useModalDialog({
    active: modelPickerOpen,
    dialogRef: modelPickerDialogRef,
    onEscape: () => {
      setModelPickerQuery("");
      setModelPickerOpen(false);
    }
  });
  const editingModel = selectedProviderModels.find(
    (model) => model.model_id === editingModelId
  ) ?? null;
  const normalizedModelPickerQuery = modelPickerQuery.trim().toLocaleLowerCase("zh-CN");
  const visibleRemoteModels = normalizedModelPickerQuery
    ? remoteModels.filter((model) =>
      model.remote_model_id.toLocaleLowerCase("zh-CN")
        .includes(normalizedModelPickerQuery)
    )
    : remoteModels;
  const currentProviderGroupName = selectedProvider?.provider_name ?? "提供方";
  const visibleRemoteModelGroups = useMemo(
    () => groupRemoteModelsBySupplier(visibleRemoteModels, currentProviderGroupName),
    [currentProviderGroupName, visibleRemoteModels]
  );
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
  const selectedProviderConnectionState = selectedProvider
    ? providerConnectionStates[selectedProvider.provider_id] ?? {
      status: "idle" as const,
      message: ""
    }
    : null;
  const activeWebApiKey = activeWebProvider
    ? webApiKeys[activeWebProvider.provider_id] ?? ""
    : "";
  const accountTone: StatusNotificationTone = accountFeedback.status === "error"
    ? "error"
    : accountFeedback.status === "success"
      ? "success"
      : "info";
  const conversationDialogTitle = conversationSettingsSections.find(
    (section) => section.key === conversationSection
  )?.label ?? "聊天设置";
  const isLabCatalogSection = activeSection === "lab-categories"
    || activeSection === "lab-items";
  const activeLabCatalog: LabCatalog = activeSection === "lab-items" ? "items" : "categories";
  const activeLabCatalogTitle = activeLabCatalog === "items"
    ? "检验指标目录"
    : "检验分类目录";
  const detailDialogTitle = activeSection === "members" ? "健康档案" : activeSection === "account"
    ? accountPanel === "profile" ? "账号资料" : accountPanel === "password" ? "密码安全" : "授权管理"
    : activeSection === "providers"
      ? selectedProvider?.provider_name ?? "模型提供方"
      : activeSection === "defaults"
        ? "默认模型"
        : activeSection === "conversation"
          ? conversationDialogTitle
          : isLabCatalogSection
            ? activeLabCatalogTitle
            : "联网工具";
  const hasSecondaryList = activeSection === "providers"
    || activeSection === "conversation"
    || isLabCatalogSection;
  const secondaryListTitle = activeSection === "providers"
    ? "模型提供方"
    : activeSection === "conversation"
      ? "聊天设置"
      : activeLabCatalogTitle;
  const editingModelTitle = editingModel
    ? editingModelPage === "root"
      ? editingModel.model_name
      : modelSettingsPageTitles[editingModelPage]
    : "";
  const toolbarTitle = editingModel
    ? editingModelTitle
    : isLabCatalogSection && detailOpen
      ? labDictionaryDetailTitle || activeLabCatalogTitle
      : hasSecondaryList && !detailOpen ? secondaryListTitle : detailDialogTitle;

  useEffect(() => {
    if (!isLabCatalogSection || !detailOpen) {
      setLabDictionaryDetailPage("root");
    }
    if (!isLabCatalogSection) setLabDictionaryDetailTitle("");
  }, [activeSection, detailOpen, isLabCatalogSection]);

  useEffect(() => {
    setExpandedModelSupplierGroups(new Set());
    setExpandedSearchModelSupplierGroups(new Set());
  }, [modelPickerOpen, selectedProviderId]);

  useEffect(() => {
    const wasOpen = previousDetailOpenRef.current;
    previousDetailOpenRef.current = detailOpen;
    if (wasOpen === detailOpen || !window.matchMedia("(max-width: 650px)").matches) {
      return;
    }

    if (detailOpen && document.activeElement instanceof HTMLElement) {
      settingsReturnFocusRef.current = document.activeElement;
    }

    const frame = window.requestAnimationFrame(() => {
      if (detailOpen) {
        settingsShellRef.current
          ?.querySelector<HTMLElement>(".settings-detail-panel-back-button")
          ?.focus({ preventScroll: true });
        return;
      }
      if (settingsReturnFocusRef.current?.isConnected) {
        settingsReturnFocusRef.current.focus({ preventScroll: true });
      }
      settingsReturnFocusRef.current = null;
    });

    return () => window.cancelAnimationFrame(frame);
  }, [detailOpen]);

  useStatusNotification(loadError, {
    id: "settings-load-error",
    title: "设置加载失败",
    tone: "error"
  });
  useStatusNotification(
    accountFeedback.status === "error" ? accountFeedback.message : "",
    {
      durationMs: 4200,
      id: "settings-account-status",
      title: "修改失败",
      tone: accountTone
    }
  );
  useStatusNotification(
    selectedProviderFeedback?.status === "error" ? selectedProviderFeedback.message : "",
    {
      id: "settings-provider-status",
      title: "模型设置未完成",
      tone: "error"
    }
  );
  useStatusNotification(modelPickerError, {
    action: {
      label: "重试",
      onClick: () => void retryLoadRemoteModels()
    },
    id: "settings-model-picker-error",
    title: "模型列表加载失败",
    tone: "error"
  });
  useStatusNotification(webFeedback.status === "error" ? webFeedback.message : "", {
    id: "settings-web-status",
    title: "联网工具设置未完成",
    tone: "error"
  });
  useStatusNotification(
    activeWebProviderFeedback?.status === "error"
      ? activeWebProviderFeedback.message
      : "",
    {
      id: "settings-web-provider-error",
      title: activeWebProvider
        ? `${activeWebProvider.provider_name} 操作未完成`
        : "联网服务操作未完成",
      tone: "error"
    }
  );

  function defaultModelOptionsForUsage(usage: DefaultModelUsage) {
    if (usage !== "vision_parse") {
      return defaultModelOptions;
    }
    return defaultModelOptions.filter((model) =>
      model.file_mime_types.some((mimeType) => mimeType.startsWith("image/"))
    );
  }

  async function toggleRemoteModel(model: RemoteModel, addedModel?: AddedModel) {
    if (!addedModel) {
      await addRemoteModel(model);
      return;
    }
    if (removingModelIds.includes(addedModel.model_id)) return;
    setRemovingModelIds((current) => [...new Set([...current, addedModel.model_id])]);
    try {
      await deleteAddedModel(addedModel.model_id);
    } finally {
      setRemovingModelIds((current) => current.filter((id) => id !== addedModel.model_id));
    }
  }

  function selectNavigationTarget(target: SettingsNavigationTarget) {
    setEditingModelId("");
    setEditingModelPage("root");
    setLabDictionaryDetailPage("root");
    if (target === "account-profile") {
      selectAccountPanel("profile");
      return;
    }
    if (target === "account-password") {
      selectAccountPanel("password");
      return;
    }
    if (target === "account-grants") {
      selectAccountPanel("grants");
      return;
    }
    if (target === "providers") {
      selectProvidersRoot();
      return;
    }
    if (target === "defaults") {
      selectDefaultsRoot();
      return;
    }
    if (target === "conversation") {
      selectConversationRoot();
      return;
    }
    if (target === "members") {
      selectMembersRoot();
      return;
    }
    if (target === "web") {
      selectWebRoot();
      return;
    }
    selectLabCatalogRoot(target === "lab-items" ? "items" : "categories");
  }

  function openModelSettings(modelId: string) {
    setEditingModelPage("root");
    setEditingModelId(modelId);
  }

  function goBackFromModelSettings() {
    if (editingModelPage !== "root") {
      setEditingModelPage("root");
      return;
    }
    setEditingModelId("");
  }

  function goBackFromLabDictionary() {
    if (labDictionaryDetailPage !== "root") {
      setLabDictionaryDetailPage("root");
      return;
    }
    closeSettingsDetail();
  }

  return (
    <>
      <section
        className="settings-shell settings-two-column"
        aria-label="账号设置"
        data-active-section={activeSection}
        data-detail-open={detailOpen ? "true" : "false"}
        data-mobile-layer={mobileLayer}
        ref={settingsShellRef}
      >
        <div className="settings-primary-pane">
          <header className="settings-primary-toolbar">
            {mobileSidebarToggle}
            <strong className="settings-primary-title">账号设置</strong>
          </header>
          <SettingsNavigation
            accountPanel={accountPanel}
            activeSection={activeSection}
            onSelect={selectNavigationTarget}
            onSignOut={onSignOut}
          />
        </div>

        <div className="settings-content-pane">
          <WorkspaceToolbar
            className="settings-toolbar"
            onBack={editingModel
              ? goBackFromModelSettings
              : isLabCatalogSection && detailOpen
                ? goBackFromLabDictionary
                : hasSecondaryList && detailOpen
                  ? closeSettingsDetail
                  : undefined}
            title={toolbarTitle}
          />
          <div className="settings-content-body">
            <div
              aria-hidden={detailOpen ? true : undefined}
              className="settings-mobile-layer-header"
              inert={detailOpen ? true : undefined}
            >
              {mobileLayer === "root" ? (
                mobileSidebarToggle ?? <span aria-hidden="true" />
              ) : (
                <button
                  aria-label="返回上一级"
                  className="control control--titlebar control--icon control--ghost workspace-back-control settings-mobile-back-button titlebar-icon-control"
                  onClick={goBackSettingsLayer}
                  type="button"
                >
                  <ChevronLeftIcon />
                </button>
              )}
              <strong>{settingsMobileLayerTitle()}</strong>
              <span aria-hidden="true" />
            </div>

            {activeSection === "conversation" ? (
              <ConversationSettingsList
                activeSection={detailOpen ? conversationSection : undefined}
                onSelect={selectConversationSection}
              />
            ) : null}

            {activeSection === "providers" ? (
              <SettingsListPanel
                bodyClassName="provider-list"
                title="模型提供方"
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
                        <div
                          className="provider-row provider-option"
                          data-active={active ? "true" : undefined}
                          key={provider.provider_id}
                        >
                          <button
                            aria-current={active ? "page" : undefined}
                            className="provider-row-select"
                            data-interaction-owner="row"
                            onClick={() => {
                              setEditingModelId("");
                              setEditingModelPage("root");
                              selectProvider(provider.provider_id);
                            }}
                            type="button"
                          >
                            <div>
                              <strong>{provider.provider_name}</strong>
                            </div>
                          </button>
                          <span className="provider-row-actions">
                            <span
                              aria-busy={connectionState.status === "testing"}
                              aria-label={providerConnectionStatusLabel(
                                provider.provider_name,
                                connectionState.status
                              )}
                              className={`provider-configured-icon provider-list-test-icon ${connectionState.status}`}
                              role="status"
                            >
                              {renderProviderTestIcon(connectionState.status)}
                            </span>
                            <SettingsListForwardIcon className="provider-row-chevron" />
                          </span>
                        </div>
                      );
                    })}
                  </GroupedList>
                ) : (
                  <p className="status-message">暂无模型提供方。</p>
                )}
              </SettingsListPanel>
            ) : null}

            {isLabCatalogSection ? (
              <LabDictionaryEditor
                catalog={activeLabCatalog}
                detailPage={labDictionaryDetailPage}
                detailOpen={detailOpen}
                onChangeCatalog={(catalog) => {
                  setLabDictionaryDetailPage("root");
                  selectLabCatalogRoot(catalog);
                }}
                onCloseDetail={closeSettingsDetail}
                onDetailTitleChange={setLabDictionaryDetailTitle}
                onNavigate={setLabDictionaryDetailPage}
                onOpenDetail={openSettingsDetail}
                onReportsChanged={onReportsChanged}
              />
            ) : null}

            {!isLabCatalogSection ? (
              <SettingsDetailPanel
                mobileOpen={detailOpen}
                onBack={editingModel ? goBackFromModelSettings : closeSettingsDetail}
                title={editingModel ? editingModelTitle : detailDialogTitle}
                wide={activeSection === "providers" || activeSection === "web"}
              >
                {editingModel ? (
                  <ModelSettingsEditor
                    model={editingModel}
                    onDelete={async () => {
                      const deleted = await deleteAddedModel(editingModel.model_id);
                      if (deleted) {
                        setEditingModelId("");
                        setEditingModelPage("root");
                      }
                      return deleted;
                    }}
                    onNavigate={setEditingModelPage}
                    onProbe={() => probeAddedModel(editingModel.model_id)}
                    onSave={(patch) => updateAddedModel(
                      editingModel.model_id,
                      patch,
                      { notify: false }
                    )}
                    providerAttachmentMimeTypes={
                      selectedProvider?.native_attachment_mime_types ?? []
                    }
                    page={editingModelPage}
                    probing={probingModelIds.includes(editingModel.model_id)}
                    supplierFallbackName={selectedProvider?.provider_id ?? "provider"}
                    saving={savingModelIds.includes(editingModel.model_id)}
                  />
                ) : (
                  <div className="settings-detail-column">
                    {activeSection === "members" ? <MembersPanel /> : null}
                    {activeSection === "account" && accountPanel === "grants" ? <MemberGrantsPanel /> : null}
                    {activeSection === "account" && accountPanel === "profile" ? (
                      <section className="settings-section">
                        <GroupedList layout="fields" density="standard">
                          <label className="field-row">
                            用户标识
                            <input
                              autoCapitalize="none"
                              autoComplete="username"
                              spellCheck={false}
                              value={accountDraft}
                              onChange={(event) => setAccountDraft(event.target.value)}
                            />
                          </label>
                          <label className="field-row">
                            账号名称
                            <input value={nameDraft} onChange={(event) => setNameDraft(event.target.value)} onCompositionEnd={(event) => syncCommittedText(event, setNameDraft)} />
                          </label>
                        </GroupedList>
                      </section>
                    ) : null}

                    {activeSection === "account" && accountPanel === "password" ? (
                      <form className="settings-section password-section" onSubmit={changePassword}>
                        <GroupedList layout="fields" density="standard">
                          <div className="secret-field field-row">
                            <label htmlFor="settings-current-password">当前密码</label>
                            <SecretInput
                              autoComplete="current-password"
                              id="settings-current-password"
                              labelForAction="当前密码"
                              name="current-password"
                              value={currentPassword}
                              onChange={(event) => setCurrentPassword(event.target.value)}
                              onCompositionEnd={(event) => syncCommittedText(event, setCurrentPassword)}
                            />
                          </div>
                          <div className="secret-field field-row">
                            <label htmlFor="settings-new-password">新密码</label>
                            <SecretInput
                              autoComplete="new-password"
                              id="settings-new-password"
                              labelForAction="新密码"
                              name="new-password"
                              value={newPassword}
                              onChange={(event) => setNewPassword(event.target.value)}
                              onCompositionEnd={(event) => syncCommittedText(event, setNewPassword)}
                            />
                          </div>
                          <div className="secret-field field-row">
                            <label htmlFor="settings-confirm-password">确认新密码</label>
                            <SecretInput
                              autoComplete="new-password"
                              id="settings-confirm-password"
                              labelForAction="确认新密码"
                              name="confirm-password"
                              value={confirmPassword}
                              onChange={(event) => setConfirmPassword(event.target.value)}
                              onCompositionEnd={(event) => syncCommittedText(event, setConfirmPassword)}
                            />
                          </div>
                        </GroupedList>
                        <button className="control control--primary command-button control-primary password-update-button" onMouseDown={keepTextControlFocused} type="submit">
                          <LockIcon />
                          <span>更新密码</span>
                        </button>
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
                              <GroupedList layout="fields" density="standard">
                                <label className="field-row">
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
                              </GroupedList>
                              <GroupedList layout="fields" className="api-credential-fields" density="standard">
                                <label className="field-row">
                                  API 地址
                                  <input
                                    value={selectedDraft.apiUrl}
                                    onChange={(event) =>
                                      updateDraft(selectedProvider.provider_id, {
                                        apiUrl: event.target.value
                                      })
                                    }
                                  />
                                </label>
                                <div className="secret-field field-row">
                                  <label htmlFor="provider-api-key">API key</label>
                                  <SecretInput
                                    autoComplete="off"
                                    id="provider-api-key"
                                    labelForAction="API key"
                                    onReveal={() => revealModelCredential(selectedProvider.provider_id)}
                                    placeholder={selectedProvider.has_api_key ? "输入新密钥以替换" : "输入 API key"}
                                    spellCheck={false}
                                    value={selectedDraft.apiKey}
                                    onChange={(event) =>
                                      updateDraft(selectedProvider.provider_id, {
                                        apiKey: event.target.value
                                      })
                                    }
                                  />
                                </div>
                                <button
                                  aria-busy={selectedProviderConnectionState?.status === "testing"}
                                  aria-label={providerConnectionTestButtonLabel(
                                    selectedProvider.provider_name,
                                    selectedProviderConnectionState?.status ?? "idle"
                                  )}
                                  className={`control control--secondary secondary-button control-primary provider-connection-test-action provider-detail-test-button ${selectedProviderConnectionState?.status ?? "idle"}`}
                                  disabled={selectedProviderConnectionState?.status === "testing"}
                                  onClick={() => void testProviderConnection(
                                    selectedProvider.provider_id,
                                    { notify: true }
                                  )}
                                  type="button"
                                >
                                  {renderProviderTestIcon(
                                    selectedProviderConnectionState?.status ?? "idle"
                                  )}
                                  <span>{connectionTestActionLabel(
                                    selectedProviderConnectionState?.status ?? "idle"
                                  )}</span>
                                </button>
                              </GroupedList>
                            </form>
                          ) : null}
                          <section
                            className={`provider-model-section${selectedProviderModels.length ? "" : " empty"}`}
                            aria-label="模型列表"
                          >
                            <div className="provider-model-content">
                              <div className="model-section-header">
                                <h2>已添加模型</h2>
                              </div>
                              <GroupedList className="model-list added-model-list" density="standard">
                                <div className="model-item add-model-item" data-grouped-list-item>
                                  <button
                                    aria-label="添加模型"
                                    className="control control--row add-model-button grouped-list-create-button"
                                    data-interaction-owner="row"
                                    onClick={() => {
                                      setModelPickerQuery("");
                                      void openAddModelModal();
                                    }}
                                    type="button"
                                  >
                                    <PlusIcon className="settings-action-icon" />
                                    <span>添加模型</span>
                                  </button>
                                </div>
                                {selectedProviderModels.map((model) => {
                                  const displayModelId = model.remote_model_id;
                                  return (
                                    <div className="model-item" data-grouped-list-item key={model.model_id}>
                                      <button
                                        aria-label={`打开模型详情：${displayModelId}`}
                                        className="model-row model-detail-row"
                                        data-interaction-owner="row"
                                        onClick={() => openModelSettings(model.model_id)}
                                        type="button"
                                      >
                                        <span>{displayModelId}</span>
                                        <span className="model-row-actions">
                                          <SettingsListForwardIcon className="model-row-chevron" />
                                        </span>
                                      </button>
                                    </div>
                                  );
                                })}
                              </GroupedList>
                              {!selectedProviderModels.length ? (
                                <p className="status-message empty-list-status provider-model-empty-status">暂未添加模型</p>
                              ) : null}
                            </div>
                            {selectedProviderModels.length ? (
                              <p className="object-list-count">共 {selectedProviderModels.length} 个模型</p>
                            ) : null}
                          </section>
                        </div>
                      </section>
                    ) : null}

                    {activeSection === "defaults" ? (
                      <section className="settings-section default-model-section">
                        <GroupedList layout="fields" className="default-model-list" density="standard">
                          {defaultModelItems.map((item) => (
                            <div className="default-model-row field-row" key={item.key}>
                              <span className="field-label">{item.label}</span>
                              <SelectPopover
                                ariaLabel={`设置${item.label}`}
                                menuWidth="content" menuAlign="end" interactionOwner="row"
                                onChange={(modelId) => updateDefaultModel(item.key, modelId)}
                                options={[
                                  { label: "不设置", value: "" },
                                  ...defaultModelOptionsForUsage(item.key).map((model) => ({
                                    label: model.model_name,
                                    value: model.model_id
                                  }))
                                ]}
                                value={item.selectedModelId}
                              />
                            </div>
                          ))}
                        </GroupedList>
                      </section>
                    ) : null}

                    {activeSection === "conversation" ? (
                      <ConversationSettingsDetail
                        activeSection={conversationSection}
                        baseContextDisplayModes={baseContextDisplayModes}
                        composerSubmitShortcut={composerSubmitShortcut}
                        contextDisplayTypes={contextDisplayTypes}
                        showContextWindowUsage={showContextWindowUsage}
                        showRelatedContent={showRelatedContent}
                        showTokenUsage={showTokenUsage}
                        toolDisplayTypes={toolDisplayTypes}
                        updateBaseContextDisplayMode={updateBaseContextDisplayMode}
                        updateComposerSubmitShortcut={updateComposerSubmitShortcut}
                        updateContextDisplayType={updateContextDisplayType}
                        updateShowRelatedContent={updateShowRelatedContent}
                        updateShowContextWindowUsage={updateShowContextWindowUsage}
                        updateShowTokenUsage={updateShowTokenUsage}
                        updateToolDisplayType={updateToolDisplayType}
                      />
                    ) : null}

                    {activeSection === "web" ? (
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
                                  disabled={activeWebProviderBusy || webFeedback.status === "saving"}
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
                                  disabled={activeWebProviderBusy}
                                  id={`web-api-key-${activeWebProvider.provider_id}`}
                                  labelForAction={`${activeWebProvider.provider_name} API key`}
                                  onReveal={() => revealWebCredential(activeWebProvider.provider_id)}
                                  placeholder={activeWebProvider.has_api_key ? "输入新密钥以替换" : "输入 API key"}
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
                                disabled={activeWebProviderBusy
                                  || (!activeWebApiKey.trim() && !activeWebProvider.has_api_key)}
                                onClick={() => void testWebProvider(activeWebProvider.provider_id)}
                                type="button"
                              >
                                {renderProviderTestIcon(activeWebProviderTestStatus)}
                                <span>{connectionTestActionLabel(activeWebProviderTestStatus)}</span>
                              </button>
                            </GroupedList>
                          </form>
                        ) : (
                          <p className="status-message">暂无可用联网服务。</p>
                        )}
                      </section>
                    ) : null}
                  </div>
                )}
              </SettingsDetailPanel>
            ) : null}
          </div>
        </div>
      </section>
      {modelPickerOpen ? createPortal(
        <RemoteModelPicker
          modelPickerDialogRef={modelPickerDialogRef}
          setModelPickerQuery={setModelPickerQuery}
          setModelPickerOpen={setModelPickerOpen}
          modelPickerLoading={modelPickerLoading}
          modelPickerError={modelPickerError}
          normalizedModelPickerQuery={normalizedModelPickerQuery}
          setExpandedSearchModelSupplierGroups={setExpandedSearchModelSupplierGroups}
          modelPickerQuery={modelPickerQuery}
          visibleRemoteModels={visibleRemoteModels}
          visibleRemoteModelGroups={visibleRemoteModelGroups}
          expandedSearchModelSupplierGroups={expandedSearchModelSupplierGroups}
          expandedModelSupplierGroups={expandedModelSupplierGroups}
          setExpandedModelSupplierGroups={setExpandedModelSupplierGroups}
          addedModels={addedModels}
          selectedProviderId={selectedProviderId}
          addingRemoteModelIds={addingRemoteModelIds}
          removingModelIds={removingModelIds}
          toggleRemoteModel={toggleRemoteModel}
          remoteModels={remoteModels}
        />,
        document.body
      ) : null}
    </>
  );
}
