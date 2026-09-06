import assert from "node:assert/strict";
import test, { describe } from "node:test";
import { loadModule } from "./helpers/load-module.mjs";

describe("conversation-preferences", () => {
  function preference(overrides = {}) {
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
      visible_context_types: [],
      tool_display_types: ["model_tool_request", "tool_call"],
      ...overrides
    };
  }

  function loadStore(remotePreference) {
    const writes = [];
    const notifications = [];
    const apiClient = {
      async fetchConversationPreferences() {
        return remotePreference;
      },
      async replaceConversationPreferences(value) {
        writes.push(structuredClone(value));
        remotePreference = structuredClone(value);
        return remotePreference;
      }
    };
    const react = {
      useCallback: callback => callback,
      useEffect() {},
      useSyncExternalStore: (_subscribe, getSnapshot) => getSnapshot()
    };
    const exports = loadModule("features/accountPreferences/conversationPreferences.ts", {}, id => {
        if (id === "../../api/authLifecycle") return { captureAuthContext: () => ({ accountId: "account-1" }), isAuthContextCurrent: () => true, subscribeAuthLifecycle: () => () => {} };
        if (id === "react") return react;
        if (id === "../../api/client") return { apiClient };
        if (id === "../../components/StatusNotificationCenter") {
          return { showStatusNotification: value => notifications.push(value) };
        }
        throw new Error(`Unexpected module: ${id}`);
      }
    );
    return { ...exports, writes, notifications };
  }

  test("conversation preferences load from the account API and save complete snapshots", async () => {
    const store = loadStore(preference({ is_related_content_visible: false }));
    assert.equal(store.readConversationPreferences("account-1").is_related_content_visible, true);
    assert.deepEqual(store.readConversationPreferences("account-1").base_context_display_modes, {
      system_prompt: "conversation_start",
      tool_catalog: "conversation_start",
      skill_catalog: "conversation_start",
      runtime_context: "conversation_start"
    });

    await store.loadConversationPreferences("account-1");
    assert.equal(store.readConversationPreferences("account-1").is_related_content_visible, false);

    store.writeConversationPreferences(
      "account-1",
      preference({
        composer_submit_shortcut: "modifier_enter",
        is_related_content_visible: false
      })
    );
    await new Promise(resolve => setTimeout(resolve, 0));
    assert.equal(store.writes.length, 1);
    assert.equal(store.writes[0].composer_submit_shortcut, "modifier_enter");
    assert.equal(store.notifications.length, 0);
  });
});

describe("composer-submit-shortcut", () => {
  function defaults() {
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
      visible_context_types: [],
      tool_display_types: ["model_tool_request", "tool_call"]
    };
  }

  function loadShortcutAdapter() {
    const preferences = new Map();
    const preferenceModule = {
      readConversationPreferences(accountId) {
        return preferences.get(accountId) ?? defaults();
      },
      useConversationPreferences(accountId) {
        return preferences.get(accountId) ?? defaults();
      },
      writeConversationPreferences(accountId, value) {
        preferences.set(accountId, value);
        return value;
      }
    };
    return { ...loadModule("features/accountPreferences/composerSubmitShortcut.ts", {}, {
      "./conversationPreferences": preferenceModule
    }), preferences };
  }

  test("composer submit shortcut defaults to Enter and updates account preferences", () => {
    const adapter = loadShortcutAdapter();
    assert.equal(adapter.useComposerSubmitShortcut("alice"), "enter");

    assert.equal(
      adapter.writeComposerSubmitShortcut("alice", "modifier_enter"),
      "modifier_enter"
    );
    assert.equal(adapter.useComposerSubmitShortcut("alice"), "modifier_enter");
    assert.equal(adapter.useComposerSubmitShortcut("bob"), "enter");
  });
});
