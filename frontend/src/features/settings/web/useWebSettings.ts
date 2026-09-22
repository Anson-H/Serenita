import { useEffect, useRef, useSyncExternalStore } from "react";
import * as webApi from "../../../api/web/webAccessApi";
import type { WebAccessSettings } from "../../../api/web/webTypes";
import { SerialTasks } from "../../../utils/serialTasks";
import { registerNavigationSave } from "../../../utils/pendingNavigation";
import { useScopedState } from "../../../utils/useScopedState";
import { settingsAutoSaveDelayMs } from "../../../utils/resourceDraft";
import { type ProviderConnectionTestState, type TestState } from "../../../utils/requestStatus";
import { beginConnectionTestRequest, connectionTestRequestIsCurrent, invalidateConnectionTestRequest } from "../../modelConfiguration/probes/settingsConnectionRequests";
import { WebProviderDrafts } from "./webProviderDrafts";

/** Account-scoped web settings session: drafts, connection tests and enablement commands. */
export function useWebSettings({ composing, isCurrentScope, serialTasks }: {
  accountId: string;
  composing: boolean;
  isCurrentScope: () => boolean;
  serialTasks: React.RefObject<SerialTasks>;
}) {
  const [webAccess, setWebAccess] = useScopedState<WebAccessSettings | null>(null, isCurrentScope);
  const [webFeedback, setWebFeedback] = useScopedState<TestState>({ status: "idle", message: "" }, isCurrentScope);
  const [webProviderFeedback, setWebProviderFeedback] = useScopedState<Record<string, TestState>>({}, isCurrentScope);
  const [webConnectionTestStates, setWebConnectionTestStates] = useScopedState<Record<string, ProviderConnectionTestState>>({}, isCurrentScope);
  const [loadError, setLoadError] = useScopedState("", isCurrentScope);
  const tests = useRef(new Map<string, AbortController>());
  const revealing = useRef(new Set<string>());
  const sequence = useRef(0);
  const draftsRef = useRef<WebProviderDrafts | null>(null);
  if (!draftsRef.current) draftsRef.current = new WebProviderDrafts({
    api: webApi, serialTasks: serialTasks.current, isCurrentScope,
    onSaved: (id, result) => setWebAccess(current => current ? {
      ...current,
      providers: current.providers.map(provider => provider.provider_id === id
        ? result.providers.find(updated => updated.provider_id === id) ?? provider : provider),
    } : result),
    onFeedback: (id, field, feedback) => field === "url" ? setWebFeedback(feedback)
      : setWebProviderFeedback(current => ({ ...current, [id]: feedback })),
  });
  const drafts = draftsRef.current;
  useSyncExternalStore(drafts.subscribe, drafts.snapshot);
  const draftSignature = JSON.stringify([drafts.values("url"), drafts.values("credential")]);
  drafts.composition(composing);

  useEffect(() => {
    if (composing) return;
    const timer = window.setTimeout(() => { void drafts.flush(); }, settingsAutoSaveDelayMs);
    return () => window.clearTimeout(timer);
  }, [draftSignature, composing, drafts]);
  useEffect(() => registerNavigationSave(() => drafts.flush()), [drafts]);
  useEffect(() => {
    drafts.resume();
    const requests = tests.current;
    return () => { drafts.dispose(); for (const request of requests.values()) request.abort(); requests.clear(); };
  }, [drafts]);
  useEffect(() => {
    void webApi.fetchWebAccessSettings().then(result => {
      if (!isCurrentScope()) return;
      drafts.receive(result); setWebAccess(result);
    }).catch(error => setLoadError(error instanceof Error ? error.message : "联网设置读取失败。"));
  }, []);

  function resetConnectionTest(id: string) {
    invalidateConnectionTestRequest(tests, id);
    setWebConnectionTestStates(current => ({ ...current, [id]: { status: "idle", message: "" } }));
    setWebProviderFeedback(current => ({ ...current, [id]: { status: "idle", message: "" } }));
  }
  function resetConnectionTests() {
    for (const id of tests.current.keys()) invalidateConnectionTestRequest(tests, id);
    setWebConnectionTestStates({}); setWebProviderFeedback({});
  }
  function updateField(id: string, field: "url" | "credential", value: string) {
    if (drafts.value(id, field) !== value) resetConnectionTest(id);
    drafts.update(id, field, value);
  }
  async function revealWebCredential(id: string) {
    const provider = webAccess?.providers.find(provider => provider.provider_id === id);
    if (!provider?.has_api_key || drafts.value(id, "credential")) return true;
    if (revealing.current.has(id)) return false;
    revealing.current.add(id);
    const revision = drafts.credentialRevision(id);
    try {
      const result = await webApi.revealWebProviderCredential(id);
      return isCurrentScope() && drafts.receiveCredential(id, result.api_key, revision);
    } catch (error) {
      setWebProviderFeedback(current => ({ ...current, [id]: { status: "error", message: error instanceof Error ? error.message : "无法读取已保存的 API key。" } }));
      return false;
    } finally { revealing.current.delete(id); }
  }
  async function updateWebSettings(patch: { is_enabled?: boolean; active_provider_id?: "tavily" | "exa" }) {
    const requestSequence = ++sequence.current;
    let requestPatch = patch;
    setWebFeedback({ status: "saving", message: "" });
    try {
      const provider = webAccess?.providers.find(item => item.provider_id === (patch.active_provider_id ?? webAccess?.active_provider_id));
      if (patch.active_provider_id && provider) resetConnectionTest(provider.provider_id);
      if ((patch.is_enabled ?? webAccess?.is_enabled) && provider) {
        const id = provider.provider_id;
        const typedCredential = Boolean(drafts.value(id, "credential").trim());
        const saved = typedCredential ? await drafts.flushField(id, "credential") : provider.has_api_key || drafts.hasCredential(id);
        if (!saved) {
          if (patch.active_provider_id) requestPatch = { ...patch, is_enabled: false };
          else {
            if (!typedCredential) setWebProviderFeedback(current => ({ ...current, [id]: { status: "error", message: "请先输入 API key。" } }));
            setWebFeedback({ status: "idle", message: "" }); return;
          }
        }
      }
      setWebAccess(current => current ? { ...current, ...requestPatch } : current);
      const result = await serialTasks.current.run("web:settings", () => webApi.updateWebAccessSettings(requestPatch), isCurrentScope);
      if (!isCurrentScope() || sequence.current !== requestSequence) return;
      setWebAccess(current => current ? { ...current, is_enabled: result.is_enabled, active_provider_id: result.active_provider_id } : result);
      setWebFeedback({ status: "idle", message: "" });
    } catch (error) {
      if (!isCurrentScope() || sequence.current !== requestSequence) return;
      setWebFeedback({ status: "error", message: error instanceof Error ? error.message : "联网工具设置保存失败。" });
    }
  }
  async function testWebProvider(id: string) {
    if (tests.current.has(id)) { resetConnectionTest(id); return; }
    if (!(await drafts.flushField(id, "url")) || !isCurrentScope()) return;
    const request = beginConnectionTestRequest(tests, id);
    const publish = (state: ProviderConnectionTestState) => {
      setWebConnectionTestStates(current => ({ ...current, [id]: state }));
      setWebProviderFeedback(current => ({ ...current, [id]: state }));
    };
    publish({ status: "testing", message: "正在测试连接..." });
    try {
      const result = await webApi.testWebProvider(id, drafts.value(id, "credential").trim() || undefined, request.signal);
      if (!isCurrentScope() || !connectionTestRequestIsCurrent(tests, id, request)) return;
      publish({ status: result.reachable ? "success" : "error", message: result.message });
    } catch (error) {
      if (!isCurrentScope() || !connectionTestRequestIsCurrent(tests, id, request)) return;
      publish({ status: "error", message: error instanceof Error ? error.message : "连接测试失败。" });
    } finally { if (connectionTestRequestIsCurrent(tests, id, request)) tests.current.delete(id); }
  }
  return {
    webAccess, webApiUrls: drafts.values("url"), webApiKeys: drafts.values("credential"),
    webFeedback, webProviderFeedback, webConnectionTestStates, resetConnectionTests,
    updateWebApiUrl: (id: string, value: string) => updateField(id, "url", value),
    updateWebApiKey: (id: string, value: string) => updateField(id, "credential", value),
    saveWebApiUrl: (id: string) => drafts.flushField(id, "url"),
    revealWebCredential, updateWebSettings, testWebProvider, loadError,
  };
}
