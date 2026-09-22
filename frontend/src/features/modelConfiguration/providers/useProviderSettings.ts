import { useModelSettingsApi } from "../ModelSettingsApi";
import { useEffect, useMemo, useRef } from "react";
import { type ProviderSummary } from "../../../api/models/modelTypes";
import { SerialTasks } from "../../../utils/serialTasks";
import { useResourceAutosave } from "../../../utils/useResourceAutosave";
import { useScopedState } from "../../../utils/useScopedState";
import { createProviderSettingsActions } from "./providerSettingsActions";
import { settingsAutoSaveDelayMs } from "../../../utils/resourceDraft";
import { type ProviderConnectionTestState, type TestState } from "../../../utils/requestStatus";
import { type ProviderDraft } from "./providerDraft";

export function useProviderSettings({
  accountId,
  composing,
  selectedProviderId,
  isCurrentScope,
  serialTasks,
}: {
  accountId: string;
  composing: boolean;
  selectedProviderId: string;
  isCurrentScope: () => boolean;
  serialTasks: React.RefObject<SerialTasks>;
}) {
  const api = useModelSettingsApi();
  const credentialDraftRevisions = useRef<Record<string, number>>({});

  const draftsRef = useRef<Record<string, ProviderDraft>>({});

  const [providers, setProviders] = useScopedState<ProviderSummary[]>(
    [],
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

  const {
    updateDraft,
    revealModelCredential,
    autoSaveProviderDraft,
    testProviderConnection,
  } = createProviderSettingsActions({
    api,
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

  const [loaded, setLoaded] = useScopedState(false, isCurrentScope);
  const [loadError, setLoadError] = useScopedState("", isCurrentScope);
  useEffect(() => {
    let active = true;
    function reload() {
      void api
        .fetchModelProviders()
        .then((result) => {
          if (!active || !isCurrentScope()) return;
          setProviders(result.providers);
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
          const retained = Object.fromEntries(Object.entries(nextDrafts).map(([id, draft]) => [id, draftsRef.current[id] ?? draft]));
          savedDraftsRef.current = Object.fromEntries(Object.entries(nextDrafts).map(([id, draft]) => [id, savedDraftsRef.current[id] ?? draft]));
          draftsRef.current = retained;
          setDrafts(retained);
          setLoadError("");
          setLoaded(true);
        })
        .catch((cause) =>
          setLoadError(
            cause instanceof Error ? cause.message : "模型提供方读取失败。",
          ),
        );
    }
    reload();
    window.addEventListener("serenita:model-configuration-changed", reload);
    return () => { active = false; window.removeEventListener("serenita:model-configuration-changed", reload); };
  }, []);

  return {
    providers,
    connectionTestStates,
    setConnectionTestStates,
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
    loaded,
  };
}
