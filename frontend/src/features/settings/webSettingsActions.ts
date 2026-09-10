import type { Dispatch, RefObject, SetStateAction } from "react";
import {
  WebAccessSettings,
  apiClient
} from "../../api/client";
import { SerialTasks } from "../../utils/serialTasks";
import { beginConnectionTestRequest, connectionTestRequestIsCurrent, invalidateConnectionTestRequest } from './settingsConnectionRequests';
import {
  type ProviderConnectionTestState,
  type TestState
} from "./settingsTypes";

type Dependencies = {
  webConnectionTestRequestsRef: RefObject<Map<string, AbortController>>;
  setWebConnectionTestStates: Dispatch<SetStateAction<Record<string, ProviderConnectionTestState>>>;
  setWebProviderFeedback: Dispatch<SetStateAction<Record<string, TestState>>>;
  credentialDraftRevisions: RefObject<Record<string, number>>;
  webApiUrlsRef: RefObject<Record<string, string>>;
  setWebApiUrls: Dispatch<SetStateAction<Record<string, string>>>;
  setDirtyWebApiUrls: Dispatch<SetStateAction<Record<string, boolean>>>;
  savedWebApiUrlsRef: RefObject<Record<string, string>>;
  webApiUrlSavePromisesRef: RefObject<Record<string, Promise<boolean>>>;
  setWebFeedback: Dispatch<SetStateAction<TestState>>;
  serialTasks: RefObject<SerialTasks>;
  isCurrentScope: () => boolean;
  setWebAccess: Dispatch<SetStateAction<WebAccessSettings | null>>;
  webApiKeysRef: RefObject<Record<string, string>>;
  setWebApiKeys: Dispatch<SetStateAction<Record<string, string>>>;
  setDirtyWebCredentials: Dispatch<SetStateAction<Record<string, boolean>>>;
  savedWebApiKeysRef: RefObject<Record<string, string>>;
  webAccess: WebAccessSettings | null;
  webApiKeys: Record<string, string>;
  revealingWebProviderIdsRef: RefObject<Set<string>>;
  webSettingsSequence: RefObject<number>;
  dirtyWebCredentials: Record<string, boolean>;
  webCredentialSavePromisesRef: RefObject<Record<string, Promise<boolean>>>;
  dirtyWebApiUrls: Record<string, boolean>;
};

export function createWebSettingsActions({
  webConnectionTestRequestsRef,
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
}: Dependencies) {
  function resetWebConnectionTest(providerId: string) {
    invalidateConnectionTestRequest(webConnectionTestRequestsRef, providerId);
    setWebConnectionTestStates((current) => ({
      ...current,
      [providerId]: { status: "idle", message: "" }
    }));
    setWebProviderFeedback((current) => ({
      ...current,
      [providerId]: { status: "idle", message: "" }
    }));
  }

  function updateWebApiUrl(providerId: string, value: string) {
    credentialDraftRevisions.current[`web:${providerId}`] = (credentialDraftRevisions.current[`web:${providerId}`] ?? 0) + 1;
    if (value !== (webApiUrlsRef.current[providerId] ?? "")) {
      resetWebConnectionTest(providerId);
    }
    webApiUrlsRef.current = { ...webApiUrlsRef.current, [providerId]: value };
    setWebApiUrls((current) => ({ ...current, [providerId]: value }));
    setDirtyWebApiUrls((current) => ({
      ...current,
      [providerId]: value.trim().replace(/\/+$/, "")
        !== (savedWebApiUrlsRef.current[providerId] ?? "")
    }));
  }

  async function saveWebApiUrl(providerId: string): Promise<boolean> {
    const pendingSave = webApiUrlSavePromisesRef.current[providerId];
    if (pendingSave) {
      const pendingSaved = await pendingSave;
      const latestApiUrl = webApiUrlsRef.current[providerId]?.trim().replace(/\/+$/, "") ?? "";
      if (!pendingSaved || latestApiUrl === savedWebApiUrlsRef.current[providerId]) {
        return pendingSaved;
      }
    }

    const apiUrl = webApiUrlsRef.current[providerId]?.trim().replace(/\/+$/, "") ?? "";
    if (!apiUrl) {
      setWebFeedback({ status: "error", message: "API 地址不能为空。" });
      return false;
    }
    if (apiUrl === savedWebApiUrlsRef.current[providerId]) {
      setDirtyWebApiUrls((current) => ({ ...current, [providerId]: false }));
      return true;
    }

    setWebFeedback({ status: "saving", message: "" });
    const savePromise = serialTasks.current.run(`web:${providerId}`, () => apiClient.updateWebProviderSettings(providerId, apiUrl), isCurrentScope)
      .then((result) => {
        if (!isCurrentScope()) return false;
        setWebAccess((current) => current ? {
          ...current,
          providers: current.providers.map(provider => provider.provider_id === providerId
            ? result.providers.find(updated => updated.provider_id === providerId) ?? provider : provider)
        } : result);
        savedWebApiUrlsRef.current = {
          ...savedWebApiUrlsRef.current,
          [providerId]: apiUrl
        };
        const latestApiUrl = webApiUrlsRef.current[providerId]?.trim().replace(/\/+$/, "") ?? "";
        if (latestApiUrl === apiUrl) {
          webApiUrlsRef.current = { ...webApiUrlsRef.current, [providerId]: apiUrl };
          setWebApiUrls((current) => ({ ...current, [providerId]: apiUrl }));
        }
        setDirtyWebApiUrls((current) => ({
          ...current,
          [providerId]: latestApiUrl !== apiUrl
        }));
        setWebFeedback({ status: "idle", message: "" });
        return true;
      })
      .catch((error) => {
        setWebFeedback({
          status: "error",
          message: error instanceof Error ? error.message : "API 地址保存失败。"
        });
        return false;
      });
    webApiUrlSavePromisesRef.current = {
      ...webApiUrlSavePromisesRef.current,
      [providerId]: savePromise
    };

    let saved = false;
    try {
      saved = await savePromise;
    } finally {
      if (webApiUrlSavePromisesRef.current[providerId] === savePromise) {
        const { [providerId]: _completedSave, ...remainingSaves } =
          webApiUrlSavePromisesRef.current;
        webApiUrlSavePromisesRef.current = remainingSaves;
      }
    }

    const latestApiUrl = webApiUrlsRef.current[providerId]?.trim().replace(/\/+$/, "") ?? "";
    if (saved && latestApiUrl && latestApiUrl !== savedWebApiUrlsRef.current[providerId]) {
      return saveWebApiUrl(providerId);
    }
    return saved;
  }

  function updateWebApiKey(providerId: string, value: string) {
    credentialDraftRevisions.current[`web:${providerId}`] = (credentialDraftRevisions.current[`web:${providerId}`] ?? 0) + 1;
    if (value !== (webApiKeysRef.current[providerId] ?? "")) {
      resetWebConnectionTest(providerId);
    }
    webApiKeysRef.current = { ...webApiKeysRef.current, [providerId]: value };
    setWebApiKeys((current) => ({ ...current, [providerId]: value }));
    setDirtyWebCredentials((current) => ({
      ...current,
      [providerId]: value.trim() !== (savedWebApiKeysRef.current[providerId] ?? "")
    }));
  }

  async function revealWebCredential(providerId: string): Promise<boolean> {
    const provider = webAccess?.providers.find((item) => item.provider_id === providerId);
    if (!provider?.has_api_key || webApiKeys[providerId]) return true;
    if (revealingWebProviderIdsRef.current.has(providerId)) return false;
    revealingWebProviderIdsRef.current.add(providerId);
    const draftRevision = credentialDraftRevisions.current[`web:${providerId}`] ?? 0;
    try {
      const result = await apiClient.revealWebProviderCredential(providerId);
      if (!isCurrentScope() || draftRevision !== (credentialDraftRevisions.current[`web:${providerId}`] ?? 0)) return false;
      const revealedApiKey = result.api_key.trim();
      const currentApiKey = webApiKeysRef.current[providerId]?.trim() ?? "";
      savedWebApiKeysRef.current = {
        ...savedWebApiKeysRef.current,
        [providerId]: revealedApiKey
      };
      if (!currentApiKey) {
        webApiKeysRef.current = {
          ...webApiKeysRef.current,
          [providerId]: result.api_key
        };
        setWebApiKeys((current) => ({ ...current, [providerId]: result.api_key }));
      }
      setDirtyWebCredentials((current) => ({
        ...current,
        [providerId]: Boolean(currentApiKey && currentApiKey !== revealedApiKey)
      }));
      return true;
    } catch (error) {
      setWebProviderFeedback((current) => ({
        ...current,
        [providerId]: {
          status: "error",
          message: error instanceof Error ? error.message : "无法读取已保存的 API key。"
        }
      }));
      return false;
    } finally {
      revealingWebProviderIdsRef.current.delete(providerId);
    }
  }

  async function updateWebSettings(patch: {
    is_enabled?: boolean;
    active_provider_id?: "tavily" | "exa";
  }) {
    const sequence = ++webSettingsSequence.current;
    let requestPatch = patch;
    setWebFeedback({ status: "saving", message: "" });
    try {
      const nextProviderId = patch.active_provider_id ?? webAccess?.active_provider_id;
      const nextIsEnabled = patch.is_enabled ?? webAccess?.is_enabled ?? false;
      const nextProvider = webAccess?.providers.find(
        (provider) => provider.provider_id === nextProviderId
      );
      if (patch.active_provider_id && nextProvider) {
        resetWebConnectionTest(nextProvider.provider_id);
        setWebProviderFeedback((current) => ({
          ...current,
          [nextProvider.provider_id]: { status: "idle", message: "" }
        }));
      }
      if (nextIsEnabled && nextProvider) {
        const providerId = nextProvider.provider_id;
        const apiKey = webApiKeysRef.current[providerId]?.trim() ?? "";
        const hasSavedCredential = nextProvider.has_api_key
          || Boolean(savedWebApiKeysRef.current[providerId]);
        const credentialNeedsSaving = Boolean(
          apiKey && (dirtyWebCredentials[providerId] || !hasSavedCredential)
        );

        if (credentialNeedsSaving) {
          const credentialSaved = await saveWebCredential(providerId);
          if (!credentialSaved) {
            if (patch.active_provider_id) {
              requestPatch = { ...patch, is_enabled: false };
            } else {
              setWebFeedback({ status: "idle", message: "" });
              return;
            }
          }
        } else if (!hasSavedCredential) {
          if (patch.active_provider_id) {
            requestPatch = { ...patch, is_enabled: false };
          } else {
            setWebProviderFeedback((current) => ({
              ...current,
              [providerId]: { status: "error", message: "请先输入 API key。" }
            }));
            setWebFeedback({ status: "idle", message: "" });
            return;
          }
        }
      }

      setWebAccess((current) => current ? { ...current, ...requestPatch } : current);
      const result = await serialTasks.current.run("web:settings", () => apiClient.updateWebAccessSettings(requestPatch), isCurrentScope);
      if (!isCurrentScope() || sequence !== webSettingsSequence.current) return;
      setWebAccess(current => current ? { ...current, is_enabled: result.is_enabled, active_provider_id: result.active_provider_id } : result);
      setWebFeedback({ status: "idle", message: "" });
    } catch (error) {
      if (!isCurrentScope() || sequence !== webSettingsSequence.current) return;
      setWebFeedback({
        status: "error",
        message: error instanceof Error ? error.message : "联网工具设置保存失败。"
      });
    }
  }

  async function saveWebCredential(providerId: string): Promise<boolean> {
    const pendingSave = webCredentialSavePromisesRef.current[providerId];
    if (pendingSave) {
      const pendingSaved = await pendingSave;
      const latestApiKey = webApiKeysRef.current[providerId]?.trim() ?? "";
      if (!pendingSaved || latestApiKey === savedWebApiKeysRef.current[providerId]) {
        return pendingSaved;
      }
    }

    const apiKey = webApiKeysRef.current[providerId]?.trim() ?? "";
    if (!apiKey) {
      setWebProviderFeedback((current) => ({
        ...current,
        [providerId]: { status: "error", message: "请输入 API key。" }
      }));
      return false;
    }
    if (apiKey === savedWebApiKeysRef.current[providerId]) {
      setDirtyWebCredentials((current) => ({ ...current, [providerId]: false }));
      return true;
    }
    setWebProviderFeedback((current) => ({
      ...current,
      [providerId]: { status: "saving", message: "正在安全保存..." }
    }));

    const savePromise = serialTasks.current.run(`web:${providerId}`, () => apiClient.saveWebProviderCredential(providerId, apiKey), isCurrentScope)
      .then((result) => {
        if (!isCurrentScope()) return false;
        setWebAccess((current) => current ? {
          ...current,
          providers: current.providers.map(provider => provider.provider_id === providerId
            ? result.providers.find(updated => updated.provider_id === providerId) ?? provider : provider)
        } : result);
        savedWebApiKeysRef.current = {
          ...savedWebApiKeysRef.current,
          [providerId]: apiKey
        };
        const latestApiKey = webApiKeysRef.current[providerId]?.trim() ?? "";
        setDirtyWebCredentials((current) => ({
          ...current,
          [providerId]: latestApiKey !== apiKey
        }));
        setWebProviderFeedback((current) => ({
          ...current,
          [providerId]: latestApiKey === apiKey
            ? { status: "success", message: "API key 已自动保存。" }
            : { status: "saving", message: "正在安全保存..." }
        }));
        return true;
      })
      .catch((error) => {
        setWebProviderFeedback((current) => ({
          ...current,
          [providerId]: {
            status: "error",
            message: error instanceof Error ? error.message : "API key 保存失败。"
          }
        }));
        return false;
      });
    webCredentialSavePromisesRef.current = {
      ...webCredentialSavePromisesRef.current,
      [providerId]: savePromise
    };

    let saved = false;
    try {
      saved = await savePromise;
    } finally {
      if (webCredentialSavePromisesRef.current[providerId] === savePromise) {
        const { [providerId]: _completedSave, ...remainingSaves } =
          webCredentialSavePromisesRef.current;
        webCredentialSavePromisesRef.current = remainingSaves;
      }
    }

    const latestApiKey = webApiKeysRef.current[providerId]?.trim() ?? "";
    if (saved && latestApiKey && latestApiKey !== savedWebApiKeysRef.current[providerId]) {
      return saveWebCredential(providerId);
    }
    return saved;
  }

  async function testWebProvider(providerId: string) {
    if (webConnectionTestRequestsRef.current.has(providerId)) {
      resetWebConnectionTest(providerId);
      return;
    }
    const apiKey = webApiKeys[providerId]?.trim() || undefined;
    if (dirtyWebApiUrls[providerId] && !(await saveWebApiUrl(providerId))) {
      return;
    }
    const request = beginConnectionTestRequest(
      webConnectionTestRequestsRef,
      providerId
    );
    setWebConnectionTestStates((current) => ({
      ...current,
      [providerId]: { status: "testing", message: "正在测试连接..." }
    }));
    setWebProviderFeedback((current) => ({
      ...current,
      [providerId]: { status: "testing", message: "正在测试连接..." }
    }));
    try {
      const result = await apiClient.testWebProvider(providerId, apiKey, request.signal);
      if (!connectionTestRequestIsCurrent(
        webConnectionTestRequestsRef,
        providerId,
        request
      )) return;
      setWebConnectionTestStates((current) => ({
        ...current,
        [providerId]: {
          status: result.reachable ? "success" : "error",
          message: result.message
        }
      }));
      setWebProviderFeedback((current) => ({
        ...current,
        [providerId]: {
          status: result.reachable ? "success" : "error",
          message: result.message
        }
      }));
    } catch (error) {
      if (!connectionTestRequestIsCurrent(
        webConnectionTestRequestsRef,
        providerId,
        request
      )) return;
      const message = error instanceof Error ? error.message : "连接测试失败。";
      setWebConnectionTestStates((current) => ({
        ...current,
        [providerId]: { status: "error", message }
      }));
      setWebProviderFeedback((current) => ({
        ...current,
        [providerId]: {
          status: "error",
          message
        }
      }));
    } finally {
      if (connectionTestRequestIsCurrent(webConnectionTestRequestsRef, providerId, request)) {
        webConnectionTestRequestsRef.current.delete(providerId);
      }
    }
  }
  return {
    updateWebApiUrl,
    saveWebApiUrl,
    updateWebApiKey,
    revealWebCredential,
    updateWebSettings,
    saveWebCredential,
    testWebProvider
  };
}
