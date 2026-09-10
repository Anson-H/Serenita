import { useCallback, useEffect, useSyncExternalStore } from "react";
import { captureAuthContext, isAuthContextCurrent, subscribeAuthLifecycle } from "../../api/authLifecycle";

import {
  apiClient,
  type ConversationPreferences
} from "../../api/client";
import { showStatusNotification } from "../../components/StatusNotificationCenter";

type PreferenceEntry = {
  loaded: boolean;
  loading: Promise<ConversationPreferences> | null;
  revision: number;
  saveQueue: Promise<void>;
  settings: ConversationPreferences;
};

const entries = new Map<string, PreferenceEntry>();
const listeners = new Map<string, Set<() => void>>();
subscribeAuthLifecycle(() => {
  entries.clear();
  for (const accountListeners of listeners.values()) accountListeners.forEach(listener => listener());
});

export function defaultConversationPreferences(): ConversationPreferences {
  return {
    composer_submit_shortcut: "enter",
    base_context_display_modes: {
      system_prompt: "conversation_start",
      tool_catalog: "conversation_start",
      skill_catalog: "conversation_start",
      runtime_context: "conversation_start"
    },
    is_context_window_usage_visible: false,
    is_related_content_visible: true,
    is_token_usage_visible: false,
    is_model_identity_visible: false,
    visible_context_types: [],
    tool_display_types: ["model_tool_request", "tool_call"]
  };
}

function copyConversationPreferences(
  preferences: ConversationPreferences
): ConversationPreferences {
  return {
    ...preferences,
    base_context_display_modes: { ...preferences.base_context_display_modes },
    visible_context_types: [...preferences.visible_context_types],
    tool_display_types: [...preferences.tool_display_types]
  };
}

function preferenceEntry(accountId: string) {
  let entry = entries.get(accountId);
  if (!entry) {
    entry = {
      loaded: false,
      loading: null,
      revision: 0,
      saveQueue: Promise.resolve(),
      settings: defaultConversationPreferences()
    };
    entries.set(accountId, entry);
  }
  return entry;
}

function notifyPreferenceListeners(accountId: string) {
  listeners.get(accountId)?.forEach((listener) => listener());
}

function preferenceErrorMessage(error: unknown) {
  return error instanceof Error && error.message
    ? error.message
    : "聊天设置暂时无法保存。";
}

export function readConversationPreferences(accountId: string) {
  return preferenceEntry(accountId).settings;
}

export function loadConversationPreferences(
  accountId: string,
  { force = false }: { force?: boolean } = {}
) {
  const context = captureAuthContext();
  if (context.accountId !== accountId) return Promise.reject(new Error("账号上下文已改变。"));
  const entry = preferenceEntry(accountId);
  if (entry.loaded && !force) {
    return Promise.resolve(entry.settings);
  }
  if (entry.loading) {
    return entry.loading;
  }
  const requestedAtRevision = entry.revision;
  const request = apiClient.fetchConversationPreferences()
    .then((preferences) => {
      if (!isAuthContextCurrent(context)) return preferences;
      if (entry.revision === requestedAtRevision) {
        entry.settings = copyConversationPreferences(preferences);
        entry.loaded = true;
        notifyPreferenceListeners(accountId);
      }
      return preferences;
    })
    .catch((error) => {
      if (!isAuthContextCurrent(context)) throw error;
      if (entry.revision === requestedAtRevision) {
        entry.loaded = false;
      }
      showStatusNotification({
        id: "conversation-preferences-load-error",
        title: "聊天设置加载失败",
        tone: "error",
        message: preferenceErrorMessage(error)
      });
      throw error;
    })
    .finally(() => {
      if (entry.loading === request) {
        entry.loading = null;
      }
    });
  entry.loading = request;
  return request;
}

export function writeConversationPreferences(
  accountId: string,
  preferences: ConversationPreferences
) {
  const context = captureAuthContext();
  if (context.accountId !== accountId) return readConversationPreferences(accountId);
  const entry = preferenceEntry(accountId);
  const next = copyConversationPreferences(preferences);
  entry.revision += 1;
  const mutationRevision = entry.revision;
  entry.loaded = true;
  entry.settings = next;
  notifyPreferenceListeners(accountId);

  const save = () => isAuthContextCurrent(context)
    ? apiClient.replaceConversationPreferences(next) : Promise.resolve(next);
  entry.saveQueue = entry.saveQueue
    .then(save, save)
    .then(
      (saved) => {
        if (isAuthContextCurrent(context) && entry.revision === mutationRevision) {
          entry.settings = copyConversationPreferences(saved);
          entry.loaded = true;
          notifyPreferenceListeners(accountId);
        }
      },
      (error) => {
        if (isAuthContextCurrent(context) && entry.revision === mutationRevision) {
          entry.loaded = false;
          showStatusNotification({
            id: "conversation-preferences-save-error",
            title: "聊天设置保存失败",
            tone: "error",
            message: preferenceErrorMessage(error)
          });
          void loadConversationPreferences(accountId, { force: true }).catch(() => undefined);
        }
      }
    );
  return next;
}

function subscribeConversationPreferences(accountId: string, listener: () => void) {
  const accountListeners = listeners.get(accountId) ?? new Set<() => void>();
  accountListeners.add(listener);
  listeners.set(accountId, accountListeners);
  return () => {
    accountListeners.delete(listener);
    if (!accountListeners.size) {
      listeners.delete(accountId);
    }
  };
}

export function useConversationPreferences(accountId: string) {
  const subscribe = useCallback(
    (listener: () => void) => subscribeConversationPreferences(accountId, listener),
    [accountId]
  );
  const getSnapshot = useCallback(
    () => readConversationPreferences(accountId),
    [accountId]
  );
  const settings = useSyncExternalStore(subscribe, getSnapshot, getSnapshot);
  useEffect(() => {
    void loadConversationPreferences(accountId).catch(() => undefined);
  }, [accountId]);
  return settings;
}
