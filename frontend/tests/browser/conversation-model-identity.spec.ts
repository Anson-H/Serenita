import { expect, test } from "@playwright/test";
import { mockWorkspace } from "../helpers/workspace";
import type { ConversationPreferences } from "../../src/api/client";

for (const width of [1280, 390]) {
  test(`model identities follow saved outputs and the account display switch at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    await mockWorkspace(page);
    let preferences: ConversationPreferences = {
      composer_submit_shortcut: "enter",
      base_context_display_modes: { system_prompt: "conversation_start", tool_catalog: "conversation_start", skill_catalog: "conversation_start", runtime_context: "conversation_start" },
      is_context_window_usage_visible: false, is_related_content_visible: true,
      is_token_usage_visible: false, is_model_identity_visible: false,
      visible_context_types: [], tool_display_types: []
    };
    await page.route("**/api/account-settings/conversation-preferences", route => {
      if (route.request().method() === "PUT") preferences = route.request().postDataJSON();
      return route.fulfill({ json: preferences });
    });
    const message = (id: string, turn: string, role: "user" | "assistant", modelId: string | null) => ({
      record_id: id, message_id: id, turn_id: turn, kind: role, role,
      parent_message_id: role === "assistant" ? `user-${turn}` : null,
      model_id: modelId, content: role === "user" ? "查看记录" : `回答 ${id}`,
      status: "completed", created_at: "2026-09-08T10:00:00+08:00", source_event_seqs: [1]
    });
    const records = [
      message("user-one", "one", "user", "selected:chat"),
      message("answer-one", "one", "assistant", "removed-provider:historical-model"),
      message("user-two", "two", "user", "selected:chat"),
      { record_id: "live-content", turn_id: "two", kind: "model", channel: "content", call_id: "live-call", purpose: "agent_action", model_id: "actual-provider:vision-model-with-a-long-identifier-to-check-mobile-wrapping", status: "streaming", value: "正在生成的回答", created_at: "2026-09-08T10:01:00+08:00" },
      message("unknown", "three", "assistant", null)
    ];
    await page.route("**/api/conversations/model-labels", route => route.fulfill({ json: {
      session_id: "model-labels", member_id: "self", member_name: "本人", title: "模型标识验收", access_state: "available",
      records, pending_turns: [], queued_inputs: [], resource_states: [], parent_session_id: null, seed_event_count: 0, fork_available: false
    } }));
    const openSettings = async () => {
      await page.goto("/setting");
      await page.locator(".settings-nav").getByRole("button", { name: "聊天设置", exact: true }).click();
      await page.getByRole("button", { name: "回答显示", exact: true }).click();
    };
    await openSettings();
    const toggle = page.getByRole("switch", { name: "显示模型标识", exact: true });
    await expect(toggle).not.toBeChecked();
    await expect(page.locator('.conversation-settings-option-list').getByRole('switch').first()).toHaveAccessibleName('显示模型标识');
    await toggle.click();
    await expect.poll(() => preferences.is_model_identity_visible).toBe(true);
    await page.goto("/chat/model-labels");
    await expect(page.getByLabel("模型标识", { exact: true }).filter({ hasText: "removed-provider:historical-model" })).toBeVisible();
    await expect(page.getByText("模型未记录", { exact: true })).toBeVisible();
    await page.locator(".turn-execution > summary").last().click();
    await expect(page.getByLabel("模型标识", { exact: true }).filter({ hasText: "actual-provider:vision-model" })).toBeVisible();
    await expect(page.getByLabel("模型标识", { exact: true }).filter({ hasText: "selected:chat" })).toHaveCount(0);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
    await page.screenshot({ path: `../artifacts/verification/conversation-model-identity-${width}.png`, fullPage: true });

    await openSettings();
    await expect(toggle).toBeChecked();
    await toggle.click();
    await expect.poll(() => preferences.is_model_identity_visible).toBe(false);
    await page.reload();
    await page.locator(".settings-nav").getByRole("button", { name: "聊天设置", exact: true }).click();
    await page.getByRole("button", { name: "回答显示", exact: true }).click();
    await expect(toggle).not.toBeChecked();
    await page.goto("/chat/model-labels");
    await expect(page.getByText("回答 answer-one", { exact: true })).toBeVisible();
    await expect(page.getByLabel("模型标识", { exact: true })).toHaveCount(0);
    await openSettings();
    await toggle.click();
    await expect.poll(() => preferences.is_model_identity_visible).toBe(true);
    await page.goto("/chat/model-labels");
    await expect(page.getByLabel("模型标识", { exact: true }).filter({ hasText: "removed-provider:historical-model" })).toBeVisible();
  });
}
