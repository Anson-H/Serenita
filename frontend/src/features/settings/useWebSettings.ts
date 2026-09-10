import { useEffect, useRef } from "react";
import { apiClient, type WebAccessSettings } from "../../api/client";
import { SerialTasks } from "../../utils/serialTasks";
import { useResourceAutosave } from "../../utils/useResourceAutosave";
import { useScopedState } from "../../utils/useScopedState";
import {
  settingsAutoSaveDelayMs,
  type ProviderConnectionTestState,
  type TestState,
} from "./settingsTypes";
import { createWebSettingsActions } from "./webSettingsActions";

export function useWebSettings({
  accountId,
  composing,
  isCurrentScope,
  serialTasks,
}: {
  accountId: string;
  composing: boolean;
  isCurrentScope: () => boolean;
  serialTasks: React.RefObject<SerialTasks>;
}) {
  const credentialDraftRevisions = useRef<Record<string, number>>({});
  const webSettingsSequence = useRef(0);

  const [webAccess, setWebAccess] = useScopedState<WebAccessSettings | null>(
    null,
    isCurrentScope,
  );

  const [webApiUrls, setWebApiUrls] = useScopedState<Record<string, string>>(
    {},
    isCurrentScope,
  );

  const [webApiKeys, setWebApiKeys] = useScopedState<Record<string, string>>(
    {},
    isCurrentScope,
  );

  const [dirtyWebApiUrls, setDirtyWebApiUrls] = useScopedState<
    Record<string, boolean>
  >({}, isCurrentScope);

  const [dirtyWebCredentials, setDirtyWebCredentials] = useScopedState<
    Record<string, boolean>
  >({}, isCurrentScope);

  const [webFeedback, setWebFeedback] = useScopedState<TestState>(
    {
      status: "idle",
      message: "",
    },
    isCurrentScope,
  );

  const [webProviderFeedback, setWebProviderFeedback] = useScopedState<
    Record<string, TestState>
  >({}, isCurrentScope);

  const [webConnectionTestStates, setWebConnectionTestStates] = useScopedState<
    Record<string, ProviderConnectionTestState>
  >({}, isCurrentScope);

  const revealingWebProviderIdsRef = useRef(new Set<string>());

  const webApiUrlsRef = useRef<Record<string, string>>({});

  const savedWebApiUrlsRef = useRef<Record<string, string>>({});

  const webApiUrlSavePromisesRef = useRef<Record<string, Promise<boolean>>>({});

  const webApiKeysRef = useRef<Record<string, string>>({});

  const savedWebApiKeysRef = useRef<Record<string, string>>({});

  const webCredentialSavePromisesRef = useRef<Record<string, Promise<boolean>>>(
    {},
  );

  const webConnectionTestRequestsRef = useRef(new Map<string, AbortController>());
  useEffect(() => {
    const requests = webConnectionTestRequestsRef.current;
    return () => {
      for (const request of requests.values()) request.abort();
      requests.clear();
    };
  }, []);

  const {
    updateWebApiUrl,
    saveWebApiUrl,
    updateWebApiKey,
    revealWebCredential,
    updateWebSettings,
    saveWebCredential,
    testWebProvider,
  } = createWebSettingsActions({
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
    dirtyWebApiUrls,
  });

  useResourceAutosave(
    Object.entries(webApiUrls).map(([id, draft]) => ({
      key: `${accountId}:web-url:${id}`,
      server: savedWebApiUrlsRef.current[id] ?? draft,
      draft,
      save: async () => {
        if (!(await saveWebApiUrl(id)))
          throw new Error("联网地址保存失败，草稿已保留。");
        return savedWebApiUrlsRef.current[id];
      },
    })),
    composing,
    settingsAutoSaveDelayMs,
  );

  useResourceAutosave(
    Object.entries(webApiKeys).map(([id, draft]) => ({
      key: `${accountId}:web-key:${id}`,
      server: savedWebApiKeysRef.current[id] ?? "",
      draft,
      save: async () => {
        if (!(await saveWebCredential(id)))
          throw new Error("联网密钥保存失败，草稿已保留。");
        return savedWebApiKeysRef.current[id];
      },
    })),
    composing,
    settingsAutoSaveDelayMs,
  );

  const [loadError, setLoadError] = useScopedState("", isCurrentScope);
  useEffect(() => {
    void apiClient
      .fetchWebAccessSettings()
      .then((result) => {
        if (!isCurrentScope()) return;
        setWebAccess(result);
        const urls = Object.fromEntries(
          result.providers.map((provider) => [
            provider.provider_id,
            provider.api_url,
          ]),
        );
        webApiUrlsRef.current = urls;
        savedWebApiUrlsRef.current = urls;
        setWebApiUrls(urls);
      })
      .catch((cause) =>
        setLoadError(
          cause instanceof Error ? cause.message : "联网设置读取失败。",
        ),
      );
  }, []);

  return {
    webAccess,
    webApiUrls,
    webApiKeys,
    webFeedback,
    webProviderFeedback,
    setWebProviderFeedback,
    webConnectionTestStates,
    setWebConnectionTestStates,
    webConnectionTestRequestsRef,
    updateWebApiUrl,
    saveWebApiUrl,
    updateWebApiKey,
    revealWebCredential,
    updateWebSettings,
    testWebProvider,
    loadError,
  };
}
