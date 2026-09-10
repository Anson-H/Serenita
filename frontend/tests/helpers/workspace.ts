import type { Page } from "@playwright/test";
import type { AddedModel } from "../../src/api/types";

export async function mockWorkspace(page: Page, models: AddedModel[] = []) {
  await page.route(url => url.pathname.startsWith("/api/"), async route => {
    const path = new URL(route.request().url()).pathname.slice(4);
    const json = (value: unknown) => route.fulfill({ json: value });
    if (path === "/conversations/attachment-capabilities") return json({ model_id: new URL(route.request().url()).searchParams.get("model_id"), file_mime_types: ["image/jpeg", "image/png", "application/pdf"] });
    if (path === "/members/access-events") return route.fulfill({ contentType: "text/event-stream", body: "retry: 60000\n\n" });
    if (path === "/notifications/events") return route.fulfill({ contentType: "text/event-stream", body: "retry: 60000\n\n" });
    if (path === "/account-settings/notifications") return json({ notifications_enabled: false, notifications_enabled_since: null, medication_due_enabled: false, medication_due_enabled_since: null, medication_expired_enabled: false, medication_expired_enabled_since: null, answer_completed_enabled: false, answer_completed_enabled_since: null, notifications_updated_at: "2026-09-08T00:00:00Z" });
    if (path === "/notifications/summary") return json({ pending_count: 0, errors: [] });
    if (path === "/notifications") return json({ items: [], next_cursor: null, errors: [] });
    // Every API request is intercepted; interactions cannot modify real account data.
    if (path === "/auth/session") return json({ authenticated: true, account_id: "test", account: "test", account_name: "测试" });
    if (path === "/members") return json({ access_revision: 1, default_member_id: "self", initial_member_id: "self", last_member_id: "self", startup_mode: "last_used", members: [{ member_id: "self", member_name: "本人", account_id: "test", owner_account: "test", is_owned: true, can_edit: true, permission: "owner", is_default: true }] });
    if (path === "/conversations") return json({ sessions: [], has_more: false, next_cursor: null });
    if (path === "/favorites") return json({ favorites: [], has_more: false, next_cursor: null });
    if (path === "/models") return json({ models });
    if (path === "/model-providers") return json({ providers: [] });
    if (path === "/model-access-settings") return json({ defaults: { chat: models[0], compact: models[0], title: models[0], vision_parse: models[0], text_embedding: null, multimodal_embedding: null } });
    if (path === "/account-settings/web-access") return json({ is_enabled: false, active_provider_id: "exa", providers: [] });
    if (path === "/account-settings/conversation-preferences") return json({ composer_submit_shortcut: "enter", base_context_display_modes: {}, is_context_window_usage_visible: false, is_related_content_visible: true, is_token_usage_visible: false, is_model_identity_visible: false, visible_context_types: [], tool_display_types: [] });
    if (path.endsWith("/reports")) return json({ reports: [], total: 0 });
    return route.fulfill({ status: 404, json: { detail: { message: `未模拟 ${path}` } } });
  });
}

