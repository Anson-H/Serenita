import { FormEvent, type ReactNode, useEffect, useMemo, useRef, useState } from "react";

import { AddedModel, ModelDefaults, ProviderSummary, RemoteModel, apiClient } from "../../api/client";
import { SettingsView } from "./SettingsView";
import {
  accountAutoSaveDelayMs,
  draftsMatch,
  userNameSpacePattern,
  type AccountPanel,
  type DefaultModelUsage,
  type ProviderConnectionTestState,
  type ProviderDraft,
  type SettingsMobileLayer,
  type SettingsSection,
  type TestState
} from "./settingsTypes";

type SettingsShellProps = {
  account: string;
  userName: string;
  mobileSidebarToggle?: ReactNode;
  onSignOut: () => void;
  onUserNameChange: (userName: string) => void;
  onModelsChanged: () => Promise<void>;
};

const emptyModelDefaults: ModelDefaults = {
  chat: null,
  title: null,
  vision_parse: null,
  compact: null
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

const providerConnectionFeedbackDurationMs = 5000;
const defaultConnectionTestState: ProviderConnectionTestState = {
  status: "idle",
  message: ""
};

export function SettingsShell({
  account,
  userName,
  mobileSidebarToggle,
  onSignOut,
  onUserNameChange,
  onModelsChanged
}: SettingsShellProps) {
  const [activeSection, setActiveSection] = useState<SettingsSection>("account");
  const [accountPanel, setAccountPanel] = useState<AccountPanel>("profile");
  const [mobileLayer, setMobileLayer] = useState<SettingsMobileLayer>("root");
  const [providers, setProviders] = useState<ProviderSummary[]>([]);
  const [selectedProviderId, setSelectedProviderId] = useState("");
  const [drafts, setDrafts] = useState<Record<string, ProviderDraft>>({});
  const savedDraftsRef = useRef<Record<string, ProviderDraft>>({});
  const [testStates, setTestStates] = useState<Record<string, TestState>>({});
  const [connectionTestStates, setConnectionTestStates] = useState<Record<string, ProviderConnectionTestState>>({});
  const [remoteModels, setRemoteModels] = useState<RemoteModel[]>([]);
  const [modelPickerOpen, setModelPickerOpen] = useState(false);
  const [modelPickerLoading, setModelPickerLoading] = useState(false);
  const [modelPickerError, setModelPickerError] = useState("");
  const [addedModels, setAddedModels] = useState<AddedModel[]>([]);
  const [modelDefaults, setModelDefaults] = useState<ModelDefaults>(emptyModelDefaults);
  const [loadError, setLoadError] = useState("");
  const [nameDraft, setNameDraft] = useState(userName);
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [accountFeedback, setAccountFeedback] = useState<TestState>({
    status: "idle",
    message: ""
  });
  const connectionFeedbackTimeoutsRef = useRef<Record<string, number>>({});

  useEffect(() => {
    setNameDraft(userName);
  }, [userName]);

  useEffect(() => {
    const trimmedName = nameDraft.trim();
    if (trimmedName === userName) {
      return;
    }
    if (!trimmedName) {
      setAccountFeedback({
        status: "error",
        message: "用户名称不能为空。"
      });
      return;
    }
    if (userNameSpacePattern.test(nameDraft)) {
      setAccountFeedback({
        status: "error",
        message: "用户名称不能包含空格。"
      });
      return;
    }

    setAccountFeedback({
      status: "saving",
      message: "保存中..."
    });

    const autosaveHandle = window.setTimeout(() => {
      void autoSaveAccountName(trimmedName);
    }, accountAutoSaveDelayMs);

    return () => window.clearTimeout(autosaveHandle);
  }, [nameDraft, userName]);

  useEffect(() => {
    void loadSettings();
  }, []);

  useEffect(() => {
    return () => {
      Object.values(connectionFeedbackTimeoutsRef.current).forEach((timeoutId) => window.clearTimeout(timeoutId));
    };
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

  useEffect(() => {
    if (activeSection !== "providers" || !providers.length) {
      return;
    }
    testAllProviderConnections(providers, drafts);
  }, [activeSection, providerIdsKey]);

  function selectAccountPanel(panel: AccountPanel) {
    setActiveSection("account");
    setAccountPanel(panel);
    setMobileLayer(panel === "profile" ? "account-profile" : "account-password");
  }

  function selectProvidersRoot() {
    setActiveSection("providers");
    setMobileLayer("provider-list");
  }

  function selectDefaultsRoot() {
    setActiveSection("defaults");
    setMobileLayer("default-models");
  }

  function selectProvider(providerId: string) {
    setActiveSection("providers");
    setSelectedProviderId(providerId);
    setRemoteModels([]);
    setModelPickerError("");
    setMobileLayer("provider-detail");
  }

  function settingsMobileLayerTitle() {
    if (mobileLayer === "provider-list") {
      return "模型提供方";
    }
    if (mobileLayer === "default-models") {
      return "默认模型";
    }
    if (mobileLayer === "account-profile") {
      return "账号资料";
    }
    if (mobileLayer === "account-password") {
      return "密码安全";
    }
    if (mobileLayer === "provider-detail") {
      return selectedProvider?.provider_name ?? "模型提供方";
    }
    return "账号设置";
  }

  function goBackSettingsLayer() {
    if (mobileLayer === "account-profile" || mobileLayer === "account-password") {
      setMobileLayer("root");
      return;
    }
    if (mobileLayer === "provider-detail") {
      setMobileLayer("provider-list");
      return;
    }
    if (mobileLayer === "default-models") {
      setMobileLayer("root");
      return;
    }
    setMobileLayer("root");
  }

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
    selectedDraft?.baseUrl,
    selectedDraft?.apiKey
  ]);

  async function loadSettings() {
    try {
      const [providerResponse, modelResponse] = await Promise.all([
        apiClient.fetchModelProviders(),
        apiClient.fetchModels()
      ]);
      const defaultsResponse = await apiClient.fetchModelDefaults();
      setProviders(providerResponse.providers);
      setAddedModels(modelResponse.models);
      setModelDefaults(defaultsResponse.defaults);
      setSelectedProviderId((current) => current || providerResponse.providers[0]?.provider_id || "");
      const nextDrafts = { ...drafts };
      for (const provider of providerResponse.providers) {
        nextDrafts[provider.provider_id] = {
          officialUrl: provider.official_url || provider.default_official_url || "",
          baseUrl: provider.base_url || provider.default_base_url || "",
          apiKey: provider.api_key || nextDrafts[provider.provider_id]?.apiKey || ""
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

  function updateDraft(providerId: string, patch: Partial<ProviderDraft>) {
    setDrafts((current) => ({
      ...current,
      [providerId]: {
        ...current[providerId],
        ...patch
      }
    }));
  }

  async function autoSaveAccountName(trimmedName: string) {
    try {
      const result = await apiClient.updateAccount(trimmedName);
      onUserNameChange(result.user_name);
      setAccountFeedback({
        status: "success",
        message: "已保存。"
      });
    } catch (error) {
      setAccountFeedback({
        status: "error",
        message: error instanceof Error ? error.message : "保存失败。"
      });
    }
  }

  async function changePassword(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!currentPassword.trim()) {
      setAccountFeedback({
        status: "error",
        message: "请输入当前密码。"
      });
      return;
    }
    if (!newPassword.trim()) {
      setAccountFeedback({
        status: "error",
        message: "新密码不能为空。"
      });
      return;
    }
    if (newPassword !== confirmPassword) {
      setAccountFeedback({
        status: "error",
        message: "两次输入的新密码不一致。"
      });
      return;
    }

    try {
      const result = await apiClient.changePassword(currentPassword, newPassword, confirmPassword);
      setCurrentPassword("");
      setNewPassword("");
      setConfirmPassword("");
      setAccountFeedback({
        status: "success",
        message: result.message
      });
    } catch (error) {
      setAccountFeedback({
        status: "error",
        message: error instanceof Error ? error.message : "密码更新失败。"
      });
    }
  }

  async function autoSaveProviderDraft(providerId: string, draft: ProviderDraft) {
    const provider = providers.find((item) => item.provider_id === providerId);
    if (!provider) {
      return;
    }
    try {
      setTestStates((current) => ({
        ...current,
        [providerId]: {
          status: "saving",
          message: "保存中..."
        }
      }));
      const shouldBecomeDefault = provider.default;
      const result = await apiClient.saveModelProvider(
        providerId,
        draft.baseUrl,
        draft.officialUrl,
        draft.apiKey,
        shouldBecomeDefault
      );
      savedDraftsRef.current = {
        ...savedDraftsRef.current,
        [providerId]: {
          officialUrl: result.official_url || draft.officialUrl,
          baseUrl: result.base_url || draft.baseUrl,
          apiKey: result.api_key ?? draft.apiKey
        }
      };
      setProviders((current) =>
        current.map((item) => (item.provider_id === providerId ? { ...item, ...result } : item))
      );
      setTestStates((current) => ({
        ...current,
        [providerId]: {
          status: "success",
          message: "已保存。"
        }
      }));
    } catch (error) {
      setTestStates((current) => ({
        ...current,
        [providerId]: {
          status: "error",
          message: error instanceof Error ? error.message : "保存失败。"
        }
      }));
    }
  }

  function setProviderConnectionTestState(providerId: string, state: ProviderConnectionTestState) {
    setConnectionTestStates((current) => ({
      ...current,
      [providerId]: state
    }));
  }

  function scheduleProviderConnectionFeedbackReset(providerId: string) {
    const existingTimeoutId = connectionFeedbackTimeoutsRef.current[providerId];
    if (existingTimeoutId) {
      window.clearTimeout(existingTimeoutId);
    }
    connectionFeedbackTimeoutsRef.current[providerId] = window.setTimeout(() => {
      setProviderConnectionTestState(providerId, defaultConnectionTestState);
      delete connectionFeedbackTimeoutsRef.current[providerId];
    }, providerConnectionFeedbackDurationMs);
  }

  function testAllProviderConnections(providerItems: ProviderSummary[], draftSource: Record<string, ProviderDraft>) {
    setConnectionTestStates((current) => {
      const next = { ...current };
      for (const provider of providerItems) {
        next[provider.provider_id] = {
          status: "idle",
          message: ""
        };
      }
      return next;
    });
    for (const provider of providerItems) {
      void testProviderConnection(provider.provider_id, {}, draftSource);
    }
  }

  async function testProviderConnection(
    providerId: string,
    options: { notify?: boolean } = {},
    draftSource: Record<string, ProviderDraft> = drafts
  ) {
    const draft = draftSource[providerId];
    if (!draft) {
      return;
    }

    setProviderConnectionTestState(providerId, {
      status: "testing",
      message: "测试连接"
    });

    try {
      const result = await apiClient.testModelProvider(
        providerId,
        draft.baseUrl,
        draft.apiKey
      );
      setProviderConnectionTestState(providerId, {
        status: result.reachable ? "success" : "error",
        message: result.reachable ? "连接成功" : "连接失败"
      });
      scheduleProviderConnectionFeedbackReset(providerId);
    } catch (error) {
      setProviderConnectionTestState(providerId, {
        status: "error",
        message: error instanceof Error ? error.message : "连接失败"
      });
      scheduleProviderConnectionFeedbackReset(providerId);
    }
  }

  async function openAddModelModal() {
    if (!selectedProvider || !selectedDraft) {
      return;
    }
    setModelPickerOpen(true);
    await loadRemoteModels();
  }

  async function loadRemoteModels() {
    if (!selectedProvider || !selectedDraft) {
      return;
    }
    const providerId = selectedProvider.provider_id;
    setModelPickerLoading(true);
    setModelPickerError("");
    setRemoteModels([]);
    try {
      await autoSaveProviderDraft(providerId, selectedDraft);
      const result = await apiClient.fetchProviderModels(providerId);
      setRemoteModels(result.models);
      setTestStates((current) => ({
        ...current,
        [providerId]: {
          status: "success",
          message: "已加载。"
        }
      }));
    } catch (error) {
      const message = error instanceof Error ? error.message : "模型列表加载失败。";
      setModelPickerError(message);
      setTestStates((current) => ({
        ...current,
        [providerId]: {
          status: "error",
          message
        }
      }));
    } finally {
      setModelPickerLoading(false);
    }
  }

  function retryLoadRemoteModels() {
    void loadRemoteModels();
  }

  async function addRemoteModel(model: RemoteModel) {
    if (!selectedProvider) {
      return;
    }
    try {
      const addedModel = await apiClient.addModel(
        selectedProvider.provider_id,
        model.remote_model_id,
        model.model_name,
        model
      );
      const modelResponse = await apiClient.fetchModels();
      setAddedModels(modelResponse.models);
      if (!chatDefaultModelId) {
        const defaultsResponse = await apiClient.updateModelDefaults({
          chat: addedModel.model_id
        });
        setModelDefaults(defaultsResponse.defaults);
      }
      await onModelsChanged();
      setTestStates((current) => ({
        ...current,
        [selectedProvider.provider_id]: {
          status: "success",
          message: "模型已添加。"
        }
      }));
    } catch (error) {
      setTestStates((current) => ({
        ...current,
        [selectedProvider.provider_id]: {
          status: "error",
          message: error instanceof Error ? error.message : "模型保存失败。"
        }
      }));
    }
  }

  async function updateDefaultModel(usage: DefaultModelUsage, nextModelId: string) {
    const previousDefaults = modelDefaults;
    try {
      const nextModel = addedModels.find((model) => model.model_id === nextModelId) ?? null;
      setModelDefaults((current) => ({
        ...current,
        [usage]: nextModel
      }));
      const defaultsResponse = await apiClient.updateModelDefaults({ [usage]: nextModelId || null });
      setModelDefaults(defaultsResponse.defaults);
      if (usage === "chat") {
        await onModelsChanged();
      }
    } catch {
      setModelDefaults(previousDefaults);
    }
  }

  async function deleteAddedModel(modelId: string) {
    if (!selectedProvider) {
      return;
    }
    try {
      await apiClient.deleteModel(modelId);
      const [modelResponse, defaultsResponse] = await Promise.all([
        apiClient.fetchModels(),
        apiClient.fetchModelDefaults()
      ]);
      setAddedModels(modelResponse.models);
      setModelDefaults(defaultsResponse.defaults);
      await onModelsChanged();
      setTestStates((current) => ({
        ...current,
        [selectedProvider.provider_id]: {
          status: "success",
          message: "模型已删除。"
        }
      }));
    } catch (error) {
      setTestStates((current) => ({
        ...current,
        [selectedProvider.provider_id]: {
          status: "error",
          message: error instanceof Error ? error.message : "模型删除失败。"
        }
      }));
    }
  }

  return (
    <SettingsView
      account={account}
      accountFeedback={accountFeedback}
      accountPanel={accountPanel}
      activeSection={activeSection}
      addedModels={addedModels}
      addRemoteModel={addRemoteModel}
      changePassword={changePassword}
      confirmPassword={confirmPassword}
      currentPassword={currentPassword}
      deleteAddedModel={deleteAddedModel}
      defaultModelItems={defaultModelItems}
      defaultModelOptions={addedModels}
      goBackSettingsLayer={goBackSettingsLayer}
      loadError={loadError}
      mobileLayer={mobileLayer}
      mobileSidebarToggle={mobileSidebarToggle}
      modelPickerError={modelPickerError}
      modelPickerLoading={modelPickerLoading}
      modelPickerOpen={modelPickerOpen}
      nameDraft={nameDraft}
      newPassword={newPassword}
      openAddModelModal={openAddModelModal}
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
      selectDefaultsRoot={selectDefaultsRoot}
      selectProvider={selectProvider}
      selectProvidersRoot={selectProvidersRoot}
      setConfirmPassword={setConfirmPassword}
      setCurrentPassword={setCurrentPassword}
      setModelPickerOpen={setModelPickerOpen}
      setNameDraft={setNameDraft}
      setNewPassword={setNewPassword}
      retryLoadRemoteModels={retryLoadRemoteModels}
      settingsMobileLayerTitle={settingsMobileLayerTitle}
      testProviderConnection={testProviderConnection}
      updateDefaultModel={updateDefaultModel}
      updateDraft={updateDraft}
    />
  );
}
