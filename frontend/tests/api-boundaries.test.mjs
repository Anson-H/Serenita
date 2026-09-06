import assert from "node:assert/strict";
import test, { describe } from "node:test";
import { loadModule } from "./helpers/load-module.mjs";

describe("api-boundaries", () => {
  for (const [status, code, eventType] of [
    [401, "SESSION_EXPIRED", "serenita:auth-session-changed"],
    [403, "MEMBER_ACCESS_UNAVAILABLE", "serenita:member-access-changed"]
  ]) {
    for (const transport of ["json", "upload", "blob", "stream"]) {
      test(`${transport} preserves ${code} and notifies the correct boundary`, async () => {
        const notifications = [];
        const body = { detail: { code, message: "request failed" } };
        class XHR {
          upload = {};
          status = status;
          responseText = JSON.stringify(body);
          open() {}
          send() { this.onload(); }
        }
        const api = loadModule("api/client.ts", {
          fetch: async () => new Response(JSON.stringify(body), { status }),
          XMLHttpRequest: XHR,
          window: { location: { origin: "http://test.local" }, dispatchEvent: e => notifications.push(e.type), localStorage: { setItem() {} } }
        });
        const call = transport === "json" ? () => api.apiClient.fetchModels()
          : transport === "upload" ? () => api.apiClient.uploadContextResource("m", null, new Blob(["file"]))
          : transport === "blob" ? () => api.apiClient.fetchReportSourceBlob("m", "r", "source")
          : () => api.apiClient.streamConversation("s", "stream", { onEvent() {} });
        await assert.rejects(call, error => error.name === "ApiRequestError" && error.status === status && error.detail.code === code);
        assert.deepEqual(notifications, [eventType]);
      });
    }
  }

  test("network diagnostics describe the actual API and cancellation stays distinguishable", async () => {
    const api = loadModule("api/request.ts", {
      fetch: async () => { throw new DOMException("cancelled", "AbortError"); }
    });
    await assert.rejects(() => api.request("/models"), error => error.name === "AbortError");
    assert.match(api.networkFailureMessage(new Error("offline")), /http:\/\/test.local\/api/);
    assert.doesNotMatch(api.networkFailureMessage(new Error("offline")), /8000|5173/);
  });

  test("non-JSON failures keep their HTTP status and member subscription closes", async () => {
    const api = loadModule("api/request.ts", { fetch: async () => new Response("bad gateway", { status: 502 }) });
    await assert.rejects(() => api.request("/models"), error => error.status === 502 && error.message.includes("502"));
    let closed = false;
    const listeners = new Map();
    class Events {
      constructor(url) { assert.equal(url, "/api/members/access-events"); }
      addEventListener(name, callback) { listeners.set(name, callback); }
      removeEventListener(name) { listeners.delete(name); }
      close() { closed = true; }
    }
    const members = loadModule("api/memberApi.ts", { EventSource: Events });
    let updates = 0;
    const unsubscribe = members.subscribeMemberAccess(() => updates++);
    listeners.get("member_access")();
    listeners.get("open")();
    unsubscribe();
    assert.equal(updates, 2);
    assert.equal(closed, true);
    assert.equal(listeners.size, 0);
  });
});

describe("favorite-api", () => {
  const loadFavoriteApi = request => loadModule("api/favoriteApi.ts", {}, { "./request": { request } });

  test("conversation-answer favorites always use the message source type", async () => {
    const calls = [];
    const api = loadFavoriteApi(async (path, options) => {
      calls.push({ options, path });
      return {};
    });

    await api.createFavorite("session-1", "message-1", ["复查"]);

    assert.deepEqual(calls, [{
      path: "/favorites",
      options: {
        method: "POST",
        body: JSON.stringify({
          source_type: "message",
          source_session_id: "session-1",
          source_id: "message-1",
          tags: ["复查"]
        })
      }
    }]);
  });
});

describe("request-ownership", () => {
  const tick = () => new Promise(resolve => setImmediate(resolve));

  test('old unauthorized responses cannot invalidate a newer login', async () => {
    const lifecycle = loadModule('api/authLifecycle.ts');
    lifecycle.setAuthenticatedAccount('a');
    let finish; const invalidations = [];
    const api = loadModule('api/request.ts', { fetch: () => new Promise(resolve => { finish = resolve; }) }, {
      './authLifecycle': lifecycle,
      './authSessionEvents': { publishAuthInvalidation: (...args) => invalidations.push(args) }
    });
    const pending = api.request('/reports');
    lifecycle.advanceAuthLifecycle('b');
    finish(new Response(JSON.stringify({ detail: { code: 'SESSION_EXPIRED', message: 'expired' } }), { status: 401 }));
    await assert.rejects(pending, error => error.name === 'AbortError');
    assert.equal(lifecycle.captureAuthContext().accountId, 'b');
    assert.deepEqual(invalidations, []);
  });

  test('all authenticated writes identify the account that initiated them', async () => {
    const lifecycle = loadModule('api/authLifecycle.ts'); lifecycle.setAuthenticatedAccount('a');
    const seen = [];
    const api = loadModule('api/request.ts', { fetch: async (_url, init) => {
      seen.push([init.method, init.headers.get('X-Serenita-Account-ID')]); return Response.json({});
    } }, { './authLifecycle': lifecycle });
    for (const method of ['POST', 'PUT', 'PATCH', 'DELETE']) await api.request('/resource', { method });
    assert.deepEqual(seen, [['POST', 'a'], ['PUT', 'a'], ['PATCH', 'a'], ['DELETE', 'a']]);
  });

  test('logout discards queued preference saves and same-account login reloads the cache', async () => {
    const lifecycle = loadModule('api/authLifecycle.ts'); lifecycle.setAuthenticatedAccount('a');
    let finish; let calls = 0; let reads = 0;
    const store = loadModule('features/accountPreferences/conversationPreferences.ts', {}, {
      '../../api/authLifecycle': lifecycle,
      '../../api/client': { apiClient: {
        replaceConversationPreferences: value => { calls++; return new Promise(resolve => { finish = () => resolve(value); }); },
        fetchConversationPreferences: async () => { reads++; return store.defaultConversationPreferences(); }
      } },
      '../../components/StatusNotificationCenter': { showStatusNotification() {} }
    });
    const draft = { ...store.defaultConversationPreferences(), composer_submit_shortcut: 'modifier_enter' };
    store.writeConversationPreferences('a', draft); await tick();
    store.writeConversationPreferences('a', { ...draft, is_token_usage_visible: true });
    lifecycle.advanceAuthLifecycle('b'); finish(); await tick();
    assert.equal(calls, 1);
    store.writeConversationPreferences('a', draft); await tick(); assert.equal(calls, 1);
    lifecycle.advanceAuthLifecycle('a');
    assert.equal(store.readConversationPreferences('a').composer_submit_shortcut, 'enter');
    await store.loadConversationPreferences('a'); assert.equal(reads, 1);
  });
});

describe("state-session-hardening", () => {
  function loadAuthSessionEvents() {
    const listeners = new Map();
    const storage = new Map();
    const window = {
      addEventListener(type, listener) {
        const current = listeners.get(type) ?? new Set();
        current.add(listener);
        listeners.set(type, current);
      },
      dispatchEvent(event) {
        for (const listener of listeners.get(event.type) ?? []) listener(event);
      },
      localStorage: {
        setItem(key, value) { storage.set(key, value); }
      },
      removeEventListener(type, listener) {
        listeners.get(type)?.delete(listener);
      }
    };
    class CustomEvent {
      constructor(type, init) {
        this.type = type;
        this.detail = init.detail;
      }
    }
    const exports = loadModule("api/authSessionEvents.ts", { window, CustomEvent });
    return {
      ...exports,
      emitStorage(value) {
        for (const listener of listeners.get("storage") ?? []) {
          listener({ key: "serenita:auth-session-change", newValue: value });
        }
      },
      storage
    };
  }

  test("auth session changes notify this tab and other tabs without storing credentials", () => {
    const events = loadAuthSessionEvents();
    const received = [];
    const unsubscribe = events.subscribeAuthSessionChanges(change => received.push(change.kind));

    events.publishAuthSessionChange("refresh");
    assert.deepEqual(received, ["refresh"]);
    const stored = [...events.storage.values()][0];
    assert.deepEqual(Object.keys(JSON.parse(stored)).sort(), ["kind", "nonce", "timestamp"]);

    events.emitStorage(JSON.stringify({ kind: "invalidated", nonce: "other-tab", timestamp: 1 }));
    assert.deepEqual(received, ["refresh", "refresh"]);
    unsubscribe();
    events.publishAuthSessionChange("refresh");
    assert.deepEqual(received, ["refresh", "refresh"]);
  });

  test("credential failures preserve a session while expired sessions invalidate it", () => {
    const events = loadAuthSessionEvents();
    const received = [];
    events.subscribeAuthSessionChanges(change => received.push(change.kind));
    events.publishAuthInvalidation(401, "SIGN_IN_FAILED");
    events.publishAuthInvalidation(403, "UNAUTHORIZED");
    assert.deepEqual(received, []);
    events.publishAuthInvalidation(401, "SESSION_EXPIRED");
    assert.deepEqual(received, ["invalidated"]);
  });
});

describe("auth-lifecycle", () => {
  test('authentication generations invalidate work even for the same account', () => {
    const api = loadModule('api/authLifecycle.ts');
    api.setAuthenticatedAccount('a');
    const first = api.captureAuthContext();
    api.advanceAuthLifecycle();
    assert.equal(api.isAuthContextCurrent(first), false);
    assert.equal(api.captureAuthContext().accountId, 'a');
    api.setAuthenticatedAccount('b');
    assert.equal(api.captureAuthContext().accountId, 'b');
  });
});

describe("settings-save-order", () => {
  test('resource write queues discard work whose page was left before dispatch', async () => {
    const { SerialTasks } = loadModule('utils/serialTasks.ts');
    const queue = new SerialTasks(); let current = true; let finish; const writes = [];
    const first = queue.run('p', () => new Promise(resolve => { finish = resolve; }), () => current);
    const second = queue.run('p', async () => { writes.push('old'); }, () => current);
    await new Promise(resolve => setImmediate(resolve)); current = false; finish();
    await first; await assert.rejects(second, error => error.name === 'AbortError'); assert.deepEqual(writes, []);
  });
});
