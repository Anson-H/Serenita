import { useEffect, useMemo, useRef } from "react";
import { apiClient, type ProviderSummary } from "../../api/client";
import { SerialTasks } from "../../utils/serialTasks";
import { useResourceAutosave } from "../../utils/useResourceAutosave";
import { useScopedState } from "../../utils/useScopedState";
import { createProviderSettingsActions } from "./providerSettingsActions";
import {
  settingsAutoSaveDelayMs,
  type ProviderConnectionTestState,
  type ProviderDraft,
  type SettingsSection,
  type TestState,
} from "./settingsTypes";

export function useProviderSettings({
  accountId,
  composing,
  activeSection,
  isCurrentScope,
  serialTasks,
}: {
  accountId: string;
  composing: boolean;
  activeSection: SettingsSection;
  isCurrentScope: () => boolean;
  serialTasks: React.RefObject<SerialTasks>;
}) {
  const credentialDraftRevisions = useRef<Record<string, number>>({});

  const draftsRef = useRef<Record<string, ProviderDraft>>({});

  const [providers, setProviders] = useScopedState<ProviderSummary[]>(
    [],
    isCurrentScope,
  );

  const [selectedProviderId, setSelectedProviderId] = useScopedState(
    "",
    isCurrentScope,
  );

  const [drafts, setDrafts] = useScopedState<Record<string, ProviderDraft>>(
    {},
    isCurrentScope,
  );

  draftsRef.current = drafts;

  const savedDraftsRef = useRef<Record<string, ProviderDraft>>({});

  const [testStates, setTestStates] = useScopedState<Record<string, TestState>>(
    {},
    isCurrentScope,
  );

  const [connectionTestStates, setConnectionTestStates] = useScopedState<
    Record<string, ProviderConnectionTestState>
  >({}, isCurrentScope);

  const [providerPageEntryVersion, setProviderPageEntryVersion] =
    useScopedState(0, isCurrentScope);

  const revealingProviderIdsRef = useRef(new Set<string>());

  const providerConnectionTestRequestsRef = useRef(new Map<string, AbortController>());
  useEffect(() => {
    const requests = providerConnectionTestRequestsRef.current;
    return () => {
      for (const request of requests.values()) request.abort();
      requests.clear();
    };
  }, []);

  const selectedProvider = useMemo(
    () =>
      providers.find((provider) => provider.provider_id === selectedProviderId),
    [providers, selectedProviderId],
  );

  const selectedDraft = selectedProvider
    ? drafts[selectedProvider.provider_id]
    : undefined;

  const selectedProviderFeedback = selectedProvider
    ? testStates[selectedProvider.provider_id]
    : undefined;

  const providerIdsKey = providers
    .map((provider) => provider.provider_id)
    .join("|");

  useEffect(() => {
    if (activeSection !== "providers" || !providers.length) {
      return;
    }
    testAllProviderConnections(providers, drafts);
  }, [activeSection, providerIdsKey, providerPageEntryVersion]);

  const {
    updateDraft,
    revealModelCredential,
    autoSaveProviderDraft,
    testAllProviderConnections,
    testProviderConnection,
  } = createProviderSettingsActions({
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
    setConnectionTestStates,
  });

  useResourceAutosave(
    Object.entries(drafts).map(([id, draft]) => ({
      key: `${accountId}:provider:${id}`,
      server: savedDraftsRef.current[id] ?? draft,
      draft,
      save: async (value: ProviderDraft) => {
        const result = await autoSaveProviderDraft(id, value);
        if (!result) throw new Error("提供方设置保存失败，草稿已保留。");
        return result;
      },
      onError: (message: string) =>
        setTestStates((current) => ({
          ...current,
          [id]: { status: "error", message },
        })),
    })),
    composing,
    settingsAutoSaveDelayMs,
  );

  const [loadError, setLoadError] = useScopedState("", isCurrentScope);
  useEffect(() => {
    void apiClient
      .fetchModelProviders()
      .then((result) => {
        if (!isCurrentScope()) return;
        setProviders(result.providers);
        setSelectedProviderId(
          (current) => current || result.providers[0]?.provider_id || "",
        );
        const nextDrafts = Object.fromEntries(
          result.providers.map((provider) => [
            provider.provider_id,
            {
              officialUrl:
                provider.official_url || provider.default_official_url || "",
              apiUrl: provider.api_url || provider.default_api_url || "",
              apiKey: "",
            },
          ]),
        );
        savedDraftsRef.current = nextDrafts;
        draftsRef.current = nextDrafts;
        setDrafts(nextDrafts);
      })
      .catch((cause) =>
        setLoadError(
          cause instanceof Error ? cause.message : "模型提供方读取失败。",
        ),
      );
  }, []);

  return {
    providers,
    selectedProviderId,
    setSelectedProviderId,
    connectionTestStates,
    setConnectionTestStates,
    setProviderPageEntryVersion,
    providerConnectionTestRequestsRef,
    selectedProvider,
    selectedDraft,
    selectedProviderFeedback,
    updateDraft,
    revealModelCredential,
    testProviderConnection,
    autoSaveProviderDraft,
    setTestStates,
    loadError,
  };
}
