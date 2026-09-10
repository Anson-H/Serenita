import type { Dispatch, RefObject, SetStateAction } from "react";
import {
  ProviderSummary,
  apiClient
} from "../../api/client";
import { showStatusNotification } from "../../components/StatusNotificationCenter";
import { SerialTasks } from "../../utils/serialTasks";
import { beginConnectionTestRequest, connectionTestRequestIsCurrent, invalidateConnectionTestRequest } from './settingsConnectionRequests';
import {
  draftsMatch,
  type ProviderConnectionTestState,
  type ProviderDraft,
  type TestState
} from "./settingsTypes";

type Dependencies = {
  credentialDraftRevisions: RefObject<Record<string, number>>;
  drafts: Record<string, ProviderDraft>;
  providerConnectionTestRequestsRef: RefObject<Map<string, AbortController>>;
  setDrafts: Dispatch<SetStateAction<Record<string, ProviderDraft>>>;
  providers: ProviderSummary[];
  revealingProviderIdsRef: RefObject<Set<string>>;
  isCurrentScope: () => boolean;
  draftsRef: RefObject<Record<string, ProviderDraft>>;
  savedDraftsRef: RefObject<Record<string, ProviderDraft>>;
  setTestStates: Dispatch<SetStateAction<Record<string, TestState>>>;
  serialTasks: RefObject<SerialTasks>;
  setProviders: Dispatch<SetStateAction<ProviderSummary[]>>;
  setConnectionTestStates: Dispatch<SetStateAction<Record<string, ProviderConnectionTestState>>>;
};

export function createProviderSettingsActions({
  credentialDraftRevisions,
  drafts,
  providerConnectionTestRequestsRef,
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
}: Dependencies) {
  function updateDraft(providerId: string, patch: Partial<ProviderDraft>) {
    credentialDraftRevisions.current[`model:${providerId}`] = (credentialDraftRevisions.current[`model:${providerId}`] ?? 0) + 1;
    const currentDraft = drafts[providerId];
    const connectionChanged = Boolean(
      currentDraft
      && (
        (patch.apiUrl !== undefined && patch.apiUrl !== currentDraft.apiUrl)
        || (patch.apiKey !== undefined && patch.apiKey !== currentDraft.apiKey)
      )
    );
    if (connectionChanged) {
      invalidateConnectionTestRequest(providerConnectionTestRequestsRef, providerId);
      setProviderConnectionTestState(providerId, { status: "idle", message: "" });
    }
    draftsRef.current = {...draftsRef.current, [providerId]: {...draftsRef.current[providerId], ...patch}};
    setDrafts(draftsRef.current);
  }

  async function revealModelCredential(providerId: string): Promise<boolean> {
    const provider = providers.find((item) => item.provider_id === providerId);
    const draft = drafts[providerId];
    if (!provider?.has_api_key || draft?.apiKey) return true;
    if (!draft) return false;
    if (revealingProviderIdsRef.current.has(providerId)) return false;
    revealingProviderIdsRef.current.add(providerId);
    const draftRevision = credentialDraftRevisions.current[`model:${providerId}`] ?? 0;
    try {
      const result = await apiClient.revealModelProviderCredential(providerId);
      if (!isCurrentScope() || draftRevision !== (credentialDraftRevisions.current[`model:${providerId}`] ?? 0) || !draftsMatch(draftsRef.current[providerId], draft)) return false;
      savedDraftsRef.current = {
        ...savedDraftsRef.current,
        [providerId]: {
          ...(savedDraftsRef.current[providerId] ?? draft),
          apiKey: result.api_key
        }
      };
      setDrafts((current) => ({
        ...current,
        [providerId]: {
          ...(current[providerId] ?? draft),
          apiKey: result.api_key
        }
      }));
      return true;
    } catch (error) {
      showStatusNotification({
        id: `provider-key-reveal-${providerId}`,
        message: error instanceof Error ? error.message : "无法读取已保存的 API key。",
        title: `${provider.provider_name} 密钥读取失败`,
        tone: "error"
      });
      return false;
    } finally {
      revealingProviderIdsRef.current.delete(providerId);
    }
  }

  async function autoSaveProviderDraft(providerId: string, draft: ProviderDraft) {
    const provider = providers.find((item) => item.provider_id === providerId);
    if (!provider) return false;
    try {
      setTestStates((current) => ({
        ...current,
        [providerId]: {
          status: "saving",
          message: "保存中..."
        }
      }));
      const result = await serialTasks.current.run(`provider:${providerId}`, () => apiClient.saveModelProvider(
        providerId, draft.apiUrl, draft.officialUrl, draft.apiKey
      ), isCurrentScope);
      if (!isCurrentScope()) return false;
      savedDraftsRef.current = {
        ...savedDraftsRef.current,
        [providerId]: {
          officialUrl: result.official_url || draft.officialUrl,
          apiUrl: result.api_url || draft.apiUrl,
          apiKey: ""
        }
      };
      setDrafts((current) => {
        const currentDraft = current[providerId];
        if (!currentDraft) {
          return current;
        }
        return {
          ...current,
          [providerId]: {
            ...currentDraft,
            officialUrl: currentDraft.officialUrl === draft.officialUrl ? result.official_url || draft.officialUrl : currentDraft.officialUrl,
            apiUrl: currentDraft.apiUrl === draft.apiUrl ? result.api_url || draft.apiUrl : currentDraft.apiUrl,
            apiKey: currentDraft.apiKey === draft.apiKey ? "" : currentDraft.apiKey
          }
        };
      });
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
      return savedDraftsRef.current[providerId];
    } catch (error) {
      setTestStates((current) => ({
        ...current,
        [providerId]: {
          status: "error",
          message: error instanceof Error ? error.message : "保存失败。"
        }
      }));
      return false;
    }
  }

  function setProviderConnectionTestState(providerId: string, state: ProviderConnectionTestState) {
    setConnectionTestStates((current) => ({
      ...current,
      [providerId]: state
    }));
  }

  function testAllProviderConnections(providerItems: ProviderSummary[], draftSource: Record<string, ProviderDraft>) {
    for (const provider of providerItems) {
      if (providerConnectionTestRequestsRef.current.has(provider.provider_id)) continue;
      void testProviderConnection(provider.provider_id, {}, draftSource);
    }
  }

  async function testProviderConnection(
    providerId: string,
    options: { notify?: boolean } = {},
    draftSource: Record<string, ProviderDraft> = drafts
  ) {
    if (providerConnectionTestRequestsRef.current.has(providerId)) {
      invalidateConnectionTestRequest(providerConnectionTestRequestsRef, providerId);
      setProviderConnectionTestState(providerId, { status: "idle", message: "" });
      return;
    }
    const draft = draftSource[providerId];
    const provider = providers.find((item) => item.provider_id === providerId);
    if (!draft) {
      return;
    }

    const request = beginConnectionTestRequest(
      providerConnectionTestRequestsRef,
      providerId
    );

    setProviderConnectionTestState(providerId, {
      status: "testing",
      message: "测试连接"
    });

    try {
      const result = await apiClient.testModelProvider(
        providerId,
        draft.apiUrl,
        draft.apiKey,
        request.signal
      );
      if (!connectionTestRequestIsCurrent(
        providerConnectionTestRequestsRef,
        providerId,
        request
      )) return;
      setProviderConnectionTestState(providerId, {
        status: result.reachable ? "success" : "error",
        message: result.reachable ? "连接成功" : "连接失败"
      });
      if (options.notify) {
        showStatusNotification({
          id: `provider-connection-${providerId}`,
          message: result.reachable ? "连接成功。" : "连接失败，请检查地址和密钥。",
          title: provider?.provider_name,
          tone: result.reachable ? "success" : "error"
        });
      }
    } catch (error) {
      if (!connectionTestRequestIsCurrent(
        providerConnectionTestRequestsRef,
        providerId,
        request
      )) return;
      const message = error instanceof Error ? error.message : "连接失败";
      setProviderConnectionTestState(providerId, {
        status: "error",
        message
      });
      if (options.notify) {
        showStatusNotification({
          id: `provider-connection-${providerId}`,
          message,
          title: provider?.provider_name ?? "模型提供方连接失败",
          tone: "error"
        });
      }
    } finally {
      if (connectionTestRequestIsCurrent(providerConnectionTestRequestsRef, providerId, request)) {
        providerConnectionTestRequestsRef.current.delete(providerId);
      }
    }
  }
  return {
    updateDraft,
    revealModelCredential,
    autoSaveProviderDraft,
    testAllProviderConnections,
    testProviderConnection
  };
}
