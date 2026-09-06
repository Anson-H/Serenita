import type { Dispatch, SetStateAction } from "react";
import { useEffect, useMemo, useRef, type ReactNode } from "react";
import {
  AddedModel,
  ModelDefaults,
  ProviderSummary,
  RemoteModel,
  WebAccessSettings,
  apiClient,
  type AuthenticatedSession
} from "../../api/client";
import { SerialTasks } from "../../utils/serialTasks";
import { useActiveScope } from "../../utils/useActiveScope";
import { useScopedState } from "../../utils/useScopedState";
import {
  useComposerSubmitShortcut
} from "../accountPreferences/composerSubmitShortcut";
import {
  useContextAssemblyDisplaySettings
} from "../accountPreferences/contextAssemblyDisplay";
import {
  useToolExecutionDisplayTypes
} from "../accountPreferences/toolExecutionDisplay";
import type { ModelCatalog } from "../modelConfiguration/modelCatalog";
import { SettingsView } from "./SettingsView";
import { createAccountSettingsActions } from './accountSettingsActions';
import { createConversationSettingsActions } from './conversationSettingsActions';
import { createDefaultModelActions } from './defaultModelActions';
import { createModelSettingsActions } from './modelSettingsActions';
import { createProviderSettingsActions } from './providerSettingsActions';
import { createSettingsNavigationActions } from './settingsNavigationActions';
import {
  accountIdentifierPattern,
  accountNameLength,
  draftsMatch,
  settingsAutoSaveDelayMs,
  type AccountPanel,
  type ConversationSettingsSection,
  type DefaultModelUsage,
  type ProviderConnectionTestState,
  type ProviderDraft,
  type SettingsMobileLayer,
  type SettingsSection,
  type TestState
} from "./settingsTypes";
import { createWebSettingsActions } from './webSettingsActions';

type SettingsShellProps = {
  accountId: string;
  account: string;
  accountName: string;
  mobileSidebarToggle?: ReactNode;
  onSignOut: () => void;
  onAccountProfileChange: (session: AuthenticatedSession) => void;
  modelCatalog: ModelCatalog;
  onModelsChanged: Dispatch<SetStateAction<ModelCatalog>>;
  onReportsChanged: () => void;
};

const defaultModelUsages: Array<{
  key: DefaultModelUsage;
  label: string;
}> = [
    { key: "chat", label: "聊天模型" },
    { key: "title", label: "标题生成模型" },
    { key: "vision_parse", label: "视觉解析模型" },
    { key: "compact", label: "压缩上下文模型" }
  ];

export function SettingsShell({
  accountId,
  account,
  accountName,
  mobileSidebarToggle,
  onSignOut,
  onAccountProfileChange,
  modelCatalog,
  onModelsChanged,
  onReportsChanged
}: SettingsShellProps) {
  const isCurrentScope = useActiveScope(accountId);
  const serialTasks = useRef(new SerialTasks());
  const credentialDraftRevisions = useRef<Record<string, number>>({});
  const webSettingsSequence = useRef(0);
  const draftsRef = useRef<Record<string, ProviderDraft>>({});
  const defaultSaveSequences = useRef<Record<string, number>>({});
  const [activeSection, setActiveSection] = useScopedState<SettingsSection>("account", isCurrentScope);
  const [accountPanel, setAccountPanel] = useScopedState<AccountPanel>("profile", isCurrentScope);
  const [conversationSection, setConversationSection] = useScopedState<ConversationSettingsSection>("composer", isCurrentScope);
  const [mobileLayer, setMobileLayer] = useScopedState<SettingsMobileLayer>("root", isCurrentScope);
  const [detailOpen, setDetailOpen] = useScopedState(false, isCurrentScope);
  const [providers, setProviders] = useScopedState<ProviderSummary[]>([], isCurrentScope);
  const [selectedProviderId, setSelectedProviderId] = useScopedState("", isCurrentScope);
  const [drafts, setDrafts] = useScopedState<Record<string, ProviderDraft>>({}, isCurrentScope);
  draftsRef.current = drafts;
  const savedDraftsRef = useRef<Record<string, ProviderDraft>>({});
  const [testStates, setTestStates] = useScopedState<Record<string, TestState>>({}, isCurrentScope);
  const [connectionTestStates, setConnectionTestStates] = useScopedState<Record<string, ProviderConnectionTestState>>({}, isCurrentScope);
  const [providerPageEntryVersion, setProviderPageEntryVersion] = useScopedState(0, isCurrentScope);
  const [remoteModels, setRemoteModels] = useScopedState<RemoteModel[]>([], isCurrentScope);
  const [modelPickerOpen, setModelPickerOpen] = useScopedState(false, isCurrentScope);
  const [modelPickerLoading, setModelPickerLoading] = useScopedState(false, isCurrentScope);
  const [modelPickerError, setModelPickerError] = useScopedState("", isCurrentScope);
  const addedModels = modelCatalog.models;
  function setAddedModels(next: SetStateAction<AddedModel[]>) {
    if (isCurrentScope()) onModelsChanged(current => ({ ...current, models: typeof next === "function" ? next(current.models) : next }));
  }
  function setModelDefaults(next: SetStateAction<ModelDefaults>) {
    if (isCurrentScope()) onModelsChanged(current => ({ ...current, defaults: typeof next === "function" ? next(current.defaults) : next }));
  }
  function publishModelCatalog(models: AddedModel[], defaults: ModelDefaults) {
    if (isCurrentScope()) onModelsChanged({ models, defaults, status: "ready", error: "" });
  }
  const [addingRemoteModelIds, setAddingRemoteModelIds] = useScopedState<string[]>([], isCurrentScope);
  const [probingModelIds, setProbingModelIds] = useScopedState<string[]>([], isCurrentScope);
  const [savingModelIds, setSavingModelIds] = useScopedState<string[]>([], isCurrentScope);
  const modelDefaults = modelCatalog.defaults;
  const composerSubmitShortcut = useComposerSubmitShortcut(accountId);
  const contextDisplaySettings = useContextAssemblyDisplaySettings(accountId);
  const toolDisplayTypes = useToolExecutionDisplayTypes(accountId);
  const [webAccess, setWebAccess] = useScopedState<WebAccessSettings | null>(null, isCurrentScope);
  const [webApiUrls, setWebApiUrls] = useScopedState<Record<string, string>>({}, isCurrentScope);
  const [webApiKeys, setWebApiKeys] = useScopedState<Record<string, string>>({}, isCurrentScope);
  const [dirtyWebApiUrls, setDirtyWebApiUrls] = useScopedState<Record<string, boolean>>({}, isCurrentScope);
  const [dirtyWebCredentials, setDirtyWebCredentials] = useScopedState<Record<string, boolean>>({}, isCurrentScope);
  const [webFeedback, setWebFeedback] = useScopedState<TestState>({
    status: "idle",
    message: ""
  }, isCurrentScope);
  const [webProviderFeedback, setWebProviderFeedback] = useScopedState<Record<string, TestState>>({}, isCurrentScope);
  const [webConnectionTestStates, setWebConnectionTestStates] = useScopedState<Record<string, ProviderConnectionTestState>>({}, isCurrentScope);
  const [loadError, setLoadError] = useScopedState("", isCurrentScope);
  const [accountDraft, setAccountDraft] = useScopedState(account, isCurrentScope);
  const [nameDraft, setNameDraft] = useScopedState(accountName, isCurrentScope);
  const [currentPassword, setCurrentPassword] = useScopedState("", isCurrentScope);
  const [newPassword, setNewPassword] = useScopedState("", isCurrentScope);
  const [confirmPassword, setConfirmPassword] = useScopedState("", isCurrentScope);
  const [accountFeedback, setAccountFeedback] = useScopedState<TestState>({
    status: "idle",
    message: ""
  }, isCurrentScope);
  const revealingProviderIdsRef = useRef(new Set<string>());
  const revealingWebProviderIdsRef = useRef(new Set<string>());
  const webApiUrlsRef = useRef<Record<string, string>>({});
  const savedWebApiUrlsRef = useRef<Record<string, string>>({});
  const webApiUrlSavePromisesRef = useRef<Record<string, Promise<boolean>>>({});
  const webApiKeysRef = useRef<Record<string, string>>({});
  const savedWebApiKeysRef = useRef<Record<string, string>>({});
  const webCredentialSavePromisesRef = useRef<Record<string, Promise<boolean>>>({});
  const providerConnectionTestRequestIdsRef = useRef(new Map<string, number>());
  const webConnectionTestRequestIdsRef = useRef(new Map<string, number>());
  const modelProbeAbortControllersRef = useRef(new Map<string, AbortController>());
  const previousAccountRef = useRef(account);
  const previousAccountNameRef = useRef(accountName);
  const accountSaveRequestIdRef = useRef(0);

  useEffect(() => {
    const previousAccount = previousAccountRef.current;
    previousAccountRef.current = account;
    setAccountDraft((current) => current === previousAccount ? account : current);
  }, [account]);

  useEffect(() => {
    const previousAccountName = previousAccountNameRef.current;
    previousAccountNameRef.current = accountName;
    setNameDraft((current) => current === previousAccountName ? accountName : current);
  }, [accountName]);

  useEffect(() => {
    const trimmedAccount = accountDraft.trim();
    const trimmedName = nameDraft.trim();
    if (trimmedAccount === account && trimmedName === accountName) {
      return;
    }
    accountSaveRequestIdRef.current += 1;
    const requestId = accountSaveRequestIdRef.current;
    if (!accountIdentifierPattern.test(trimmedAccount)) {
      setAccountFeedback({
        status: "error",
        message: "用户标识只能包含字母、数字、下划线和短横线，长度不超过 20。"
      });
      return;
    }
    if (trimmedAccount.toLowerCase() === "all_users") {
      setAccountFeedback({
        status: "error",
        message: "该用户标识不可使用。"
      });
      return;
    }
    if (!trimmedName) {
      setAccountFeedback({
        status: "error",
        message: "账号名称不能为空。"
      });
      return;
    }
    if (accountNameLength(trimmedName) > 50) {
      setAccountFeedback({
        status: "error",
        message: "账号名称不能超过 50 个字符。"
      });
      return;
    }

    setAccountFeedback({
      status: "saving",
      message: "保存中..."
    });

    const autosaveHandle = window.setTimeout(() => {
      void autoSaveAccountProfile(trimmedAccount, trimmedName, requestId);
    }, settingsAutoSaveDelayMs);

    return () => window.clearTimeout(autosaveHandle);
  }, [account, accountDraft, nameDraft, accountName]);

  useEffect(() => {
    void loadSettings();
  }, []);

  const selectedProvider = useMemo(
    () => providers.find((provider) => provider.provider_id === selectedProviderId),
    [providers, selectedProviderId]
  );
  const selectedDraft = selectedProvider ? drafts[selectedProvider.provider_id] : undefined;
  const selectedProviderModels = selectedProvider
    ? addedModels.filter((model) => model.provider_id === selectedProvider.provider_id)
    : [];
  const selectedProviderFeedback = selectedProvider ? testStates[selectedProvider.provider_id] : undefined;
  const defaultModelItems = defaultModelUsages.map((item) => ({
    ...item,
    selectedModelId: modelDefaults[item.key]?.model_id ?? ""
  }));
  const chatDefaultModelId = modelDefaults.chat?.model_id ?? "";
  const providerIdsKey = providers.map((provider) => provider.provider_id).join("|");
  const dirtyWebCredentialIds = Object.entries(dirtyWebCredentials)
    .filter(([, dirty]) => dirty)
    .map(([providerId]) => providerId)
    .sort();
  const dirtyWebCredentialIdsKey = dirtyWebCredentialIds.join("|");
  const dirtyWebApiUrlIds = Object.entries(dirtyWebApiUrls)
    .filter(([, dirty]) => dirty)
    .map(([providerId]) => providerId)
    .sort();
  const dirtyWebApiUrlIdsKey = dirtyWebApiUrlIds.join("|");

  useEffect(() => {
    if (activeSection !== "providers" || !providers.length) {
      return;
    }
    testAllProviderConnections(providers, drafts);
  }, [activeSection, providerIdsKey, providerPageEntryVersion]);

  useEffect(() => {
    if (activeSection !== "web" || !dirtyWebCredentialIds.length) {
      return;
    }
    const providerIds = dirtyWebCredentialIds.filter(
      (providerId) => Boolean(webApiKeys[providerId]?.trim())
    );
    if (!providerIds.length) {
      return;
    }
    const autosaveHandle = window.setTimeout(() => {
      providerIds.forEach((providerId) => void saveWebCredential(providerId));
    }, settingsAutoSaveDelayMs);
    return () => window.clearTimeout(autosaveHandle);
  }, [activeSection, dirtyWebCredentialIdsKey, webApiKeys]);

  useEffect(() => {
    if (activeSection !== "web" || !dirtyWebApiUrlIds.length) {
      return;
    }
    const autosaveHandle = window.setTimeout(() => {
      dirtyWebApiUrlIds.forEach((providerId) => void saveWebApiUrl(providerId));
    }, settingsAutoSaveDelayMs);
    return () => window.clearTimeout(autosaveHandle);
  }, [activeSection, dirtyWebApiUrlIdsKey, webApiUrls]);

  useEffect(() => {
    if (activeSection !== "providers" || !selectedProvider || !selectedDraft) {
      return;
    }
    if (draftsMatch(savedDraftsRef.current[selectedProvider.provider_id], selectedDraft)) {
      return;
    }

    const autosaveHandle = window.setTimeout(() => {
      void autoSaveProviderDraft(selectedProvider.provider_id, selectedDraft);
    }, 650);

    return () => window.clearTimeout(autosaveHandle);
  }, [
    activeSection,
    selectedProvider?.provider_id,
    selectedDraft?.officialUrl,
    selectedDraft?.apiUrl,
    selectedDraft?.apiKey
  ]);

  async function loadSettings() {
    try {
      const [providerResponse, modelResponse, webResponse] = await Promise.all([
        apiClient.fetchModelProviders(),
        apiClient.fetchModels(),
        apiClient.fetchWebAccessSettings()
      ]);
      const defaultsResponse = await apiClient.fetchModelDefaults();
      setProviders(providerResponse.providers);
      publishModelCatalog(modelResponse.models, defaultsResponse.defaults);
      setWebAccess(webResponse);
      const nextWebApiUrls = Object.fromEntries(
        webResponse.providers.map((provider) => [provider.provider_id, provider.api_url])
      );
      webApiUrlsRef.current = nextWebApiUrls;
      savedWebApiUrlsRef.current = nextWebApiUrls;
      setWebApiUrls(nextWebApiUrls);
      setDirtyWebApiUrls({});
      setSelectedProviderId((current) => current || providerResponse.providers[0]?.provider_id || "");
      const nextDrafts = { ...drafts };
      for (const provider of providerResponse.providers) {
        nextDrafts[provider.provider_id] = {
          officialUrl: provider.official_url || provider.default_official_url || "",
          apiUrl: provider.api_url || provider.default_api_url || "",
          apiKey: nextDrafts[provider.provider_id]?.apiKey || ""
        };
      }
      savedDraftsRef.current = nextDrafts;
      setDrafts(nextDrafts);
      if (activeSection === "providers") {
        testAllProviderConnections(providerResponse.providers, nextDrafts);
      }
    } catch (error) {
      setLoadError(error instanceof Error ? error.message : "模型提供方加载失败");
    }
  }
  const { autoSaveAccountProfile, changePassword } = createAccountSettingsActions({
    serialTasks,
    isCurrentScope,
    accountSaveRequestIdRef,
    onAccountProfileChange,
    setAccountDraft,
    setNameDraft,
    setAccountFeedback,
    currentPassword,
    newPassword,
    confirmPassword,
    setCurrentPassword,
    setNewPassword,
    setConfirmPassword
  });
  const { updateDraft, revealModelCredential, autoSaveProviderDraft, testAllProviderConnections, testProviderConnection } = createProviderSettingsActions({
    credentialDraftRevisions,
    drafts,
    providerConnectionTestRequestIdsRef,
    setDrafts,
    providers,
    revealingProviderIdsRef,
    isCurrentScope,
    draftsRef,
    savedDraftsRef,
    setTestStates,
    serialTasks,
    setProviders,
    setConnectionTestStates
  });
  const { openAddModelModal, retryLoadRemoteModels, addRemoteModel, probeAddedModel, updateAddedModel, deleteAddedModel } = createModelSettingsActions({
    selectedProvider,
    selectedDraft,
    setModelPickerOpen,
    setModelPickerLoading,
    setModelPickerError,
    setRemoteModels,
    autoSaveProviderDraft,
    setTestStates,
    setAddingRemoteModelIds,
    setAddedModels,
    chatDefaultModelId,
    setModelDefaults,
    modelProbeAbortControllersRef,
    setProbingModelIds,
    publishModelCatalog,
    setSavingModelIds
  });
  const { updateDefaultModel } = createDefaultModelActions({ defaultSaveSequences, addedModels, setModelDefaults, serialTasks, isCurrentScope });
  const { updateWebApiUrl, saveWebApiUrl, updateWebApiKey, revealWebCredential, updateWebSettings, saveWebCredential, testWebProvider } = createWebSettingsActions({
    webConnectionTestRequestIdsRef,
    setWebConnectionTestStates,
    setWebProviderFeedback,
    credentialDraftRevisions,
    webApiUrlsRef,
    setWebApiUrls,
    setDirtyWebApiUrls,
    savedWebApiUrlsRef,
    webApiUrlSavePromisesRef,
    setWebFeedback,
    serialTasks,
    isCurrentScope,
    setWebAccess,
    webApiKeysRef,
    setWebApiKeys,
    setDirtyWebCredentials,
    savedWebApiKeysRef,
    webAccess,
    webApiKeys,
    revealingWebProviderIdsRef,
    webSettingsSequence,
    dirtyWebCredentials,
    webCredentialSavePromisesRef,
    dirtyWebApiUrls
  });
  const {
    selectAccountPanel,
    selectProvidersRoot,
    selectDefaultsRoot,
    selectConversationRoot,
    selectConversationSection,
    selectMembersRoot,
    selectWebRoot,
    selectLabCatalogRoot,
    openSettingsDetail,
    selectProvider,
    closeSettingsDetail,
    settingsMobileLayerTitle,
    goBackSettingsLayer
  } = createSettingsNavigationActions({
    setActiveSection,
    setAccountPanel,
    setMobileLayer,
    setDetailOpen,
    providers,
    providerConnectionTestRequestIdsRef,
    setConnectionTestStates,
    setProviderPageEntryVersion,
    setConversationSection,
    webAccess,
    webConnectionTestRequestIdsRef,
    setWebConnectionTestStates,
    setWebProviderFeedback,
    activeSection,
    setSelectedProviderId,
    setRemoteModels,
    setModelPickerError,
    mobileLayer
  });
  const {
    updateContextDisplayType,
    updateComposerSubmitShortcut,
    updateBaseContextDisplayMode,
    updateShowContextWindowUsage,
    updateShowRelatedContent,
    updateShowTokenUsage,
    updateToolDisplayType
  } = createConversationSettingsActions({ accountId, contextDisplaySettings, toolDisplayTypes });

  return (
    <SettingsView
      accountDraft={accountDraft}
      accountFeedback={accountFeedback}
      accountPanel={accountPanel}
      activeSection={activeSection}
      addedModels={addedModels}
      addRemoteModel={addRemoteModel}
      addingRemoteModelIds={addingRemoteModelIds}
      changePassword={changePassword}
      confirmPassword={confirmPassword}
      conversationSection={conversationSection}
      composerSubmitShortcut={composerSubmitShortcut}
      baseContextDisplayModes={contextDisplaySettings.baseModes}
      contextDisplayTypes={contextDisplaySettings.visibleContextTypes}
      showContextWindowUsage={contextDisplaySettings.showContextWindowUsage}
      showRelatedContent={contextDisplaySettings.showRelatedContent}
      showTokenUsage={contextDisplaySettings.showTokenUsage}
      toolDisplayTypes={toolDisplayTypes}
      currentPassword={currentPassword}
      deleteAddedModel={deleteAddedModel}
      defaultModelItems={defaultModelItems}
      defaultModelOptions={addedModels}
      detailOpen={detailOpen}
      closeSettingsDetail={closeSettingsDetail}
      goBackSettingsLayer={goBackSettingsLayer}
      loadError={loadError}
      mobileLayer={mobileLayer}
      mobileSidebarToggle={mobileSidebarToggle}
      modelPickerError={modelPickerError}
      modelPickerLoading={modelPickerLoading}
      modelPickerOpen={modelPickerOpen}
      probingModelIds={probingModelIds}
      probeAddedModel={probeAddedModel}
      nameDraft={nameDraft}
      newPassword={newPassword}
      openAddModelModal={openAddModelModal}
      onReportsChanged={onReportsChanged}
      onSignOut={onSignOut}
      providerConnectionStates={connectionTestStates}
      providers={providers}
      remoteModels={remoteModels}
      selectedDraft={selectedDraft}
      selectedProvider={selectedProvider}
      selectedProviderFeedback={selectedProviderFeedback}
      selectedProviderId={selectedProviderId}
      selectedProviderModels={selectedProviderModels}
      selectAccountPanel={selectAccountPanel}
      selectConversationRoot={selectConversationRoot}
      selectConversationSection={selectConversationSection}
      selectDefaultsRoot={selectDefaultsRoot}
      selectLabCatalogRoot={selectLabCatalogRoot}
      openSettingsDetail={openSettingsDetail}
      selectProvider={selectProvider}
      selectProvidersRoot={selectProvidersRoot}
      setConfirmPassword={setConfirmPassword}
      setCurrentPassword={setCurrentPassword}
      setAccountDraft={setAccountDraft}
      setModelPickerOpen={setModelPickerOpen}
      setNameDraft={setNameDraft}
      setNewPassword={setNewPassword}
      retryLoadRemoteModels={retryLoadRemoteModels}
      revealModelCredential={revealModelCredential}
      revealWebCredential={revealWebCredential}
      settingsMobileLayerTitle={settingsMobileLayerTitle}
      testProviderConnection={testProviderConnection}
      savingModelIds={savingModelIds}
      updateDefaultModel={updateDefaultModel}
      updateBaseContextDisplayMode={updateBaseContextDisplayMode}
      updateComposerSubmitShortcut={updateComposerSubmitShortcut}
      updateContextDisplayType={updateContextDisplayType}
      updateShowRelatedContent={updateShowRelatedContent}
      updateShowContextWindowUsage={updateShowContextWindowUsage}
      updateShowTokenUsage={updateShowTokenUsage}
      updateToolDisplayType={updateToolDisplayType}
      updateDraft={updateDraft}
      updateAddedModel={updateAddedModel}
      updateWebApiKey={updateWebApiKey}
      updateWebSettings={updateWebSettings}
      selectWebRoot={selectWebRoot}
      selectMembersRoot={selectMembersRoot}
      webAccess={webAccess}
      webApiUrls={webApiUrls}
      webApiKeys={webApiKeys}
      webFeedback={webFeedback}
      webConnectionTestStates={webConnectionTestStates}
      webProviderFeedback={webProviderFeedback}
      saveWebApiUrl={saveWebApiUrl}
      testWebProvider={testWebProvider}
      updateWebApiUrl={updateWebApiUrl}
    />
  );
}
