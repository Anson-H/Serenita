import { expect, test, type Route } from "@playwright/test";
import { mockWorkspace } from "../helpers/workspace";
import type { AddedModel } from "../../src/api/types";

const profile = { availability: "available" as const, supports_text: true, supports_tool_calling: true, file_mime_types: [] };
const model: AddedModel = { model_id: "test:model", remote_model_id: "model", provider_id: "test", model_name: "测试模型", supports_text: true, supports_tool_calling: true, file_mime_types: [], thinking_modes: ["non_thinking"], capability_profiles: { default_state: "non_thinking", non_thinking: profile, thinking: { ...profile, availability: "unavailable" } }, context_window_tokens: 32000, max_output_tokens: 8000 };

test("accepted messages leave an empty new chat while other conversations and list reads are pending", async ({ page }) => {
  await mockWorkspace(page, [model]);
  let sent = 0;
  let detailsRead = 0;
  await page.route("**/api/conversations/messages", route => {
    const id = String(++sent);
    return route.fulfill({ json: {
      disposition: "started", session_id: id, member_id: "self", member_name: "本人", title: `会话 ${id}`,
      turn_id: `turn-${id}`, stream_id: `stream-${id}`, user_message_id: `user-${id}`,
      final_assistant_message_id: `answer-${id}`, model_id: model.model_id, message_status: "streaming",
      created_at: "2026-09-07T00:00:00+08:00"
    } });
  });
  await page.route(/\/api\/conversations\/\d+\/streams\//, () => {});
  await page.route(/\/api\/conversations\/\d+$/, route => {
    detailsRead++;
    const id = new URL(route.request().url()).pathname.split("/").at(-1);
    return route.fulfill({ json: {
      session_id: id, member_id: "self", member_name: "本人", title: `会话 ${id}`, access_state: "available",
      records: [], pending_turns: [], queued_inputs: [], resource_states: [], parent_session_id: null, seed_event_count: 0, fork_available: false
    } });
  });
  await page.goto("/");
  const composer = page.locator(".conversation-composer textarea");
  await expect(composer).toBeEnabled();
  // Keep background reads pending: navigation and typing must remain independent.
  await page.route("**/api/conversations", () => {});
  for (let index = 1; index <= 8; index++) {
    await composer.fill(`已发送的文字 ${index}`);
    await page.getByRole("button", { name: "发送", exact: true }).click();
    await expect(page).toHaveURL(new RegExp(`/chat/${index}$`));
    await page.getByRole("button", { name: "发起新聊天", exact: true }).click();
    await expect(composer).toBeEnabled();
    await expect(composer).toHaveValue("");
  }
  expect(detailsRead, "accepted responses already contain the initial conversation state").toBe(0);
  await page.locator(".conversation-title-button").filter({ hasText: "会话 1" }).click();
  await expect(page).toHaveURL(/\/chat\/1$/);
  await expect.poll(() => detailsRead).toBe(1);
  await page.getByRole("button", { name: "发起新聊天", exact: true }).click();
  await composer.fill("新的未发送草稿");
  await expect(composer).toHaveValue("新的未发送草稿");
});

for (const initialPath of ["/", "/chat/existing"]) {
  test(`new chat unlocks a pending submission and ignores its late response from ${initialPath}`, async ({ page }) => {
    await mockWorkspace(page, [model]);
    await page.route("**/api/conversations/existing", route => route.fulfill({ json: {
      session_id: "existing", member_id: "self", member_name: "本人", title: "已有聊天", access_state: "available",
      records: [], pending_turns: [], queued_inputs: [], resource_states: [], parent_session_id: null, seed_event_count: 0, fork_available: false
    } }));
    const pending: Route[] = [];
    await page.route("**/api/conversations/messages", route => { pending.push(route); });
    const errors: string[] = [];
    page.on("pageerror", error => errors.push(error.message));
    await page.goto(initialPath);
    const composer = page.locator(".conversation-composer textarea");
    for (let index = 0; index < 8; index++) {
      await composer.fill(`消息 ${index}`);
      await page.getByRole("button", { name: "发送", exact: true }).click();
      await expect.poll(() => pending.length).toBe(index + 1);
      await expect(composer).toBeDisabled();
      await page.getByRole("button", { name: "发起新聊天", exact: true }).click();
      await expect(composer).toBeEnabled();
      await expect(page).toHaveURL(/\/$/);
    }
    await composer.fill("当前正在发送的消息");
    await page.getByRole("button", { name: "发送", exact: true }).click();
    await expect.poll(() => pending.length).toBe(9);
    for (const [index, request] of pending.slice(0, 8).entries()) {
      await request.fulfill({ json: {
        disposition: "started", session_id: `late-${index}`, member_id: "self", member_name: "本人", title: "旧请求",
        turn_id: `turn-${index}`, stream_id: `stream-${index}`, user_message_id: `user-${index}`,
        final_assistant_message_id: `answer-${index}`, model_id: model.model_id, message_status: "streaming", content: "旧消息", created_at: "2026-09-07T00:00:00+08:00"
      } });
    }
    await expect(composer).toHaveValue("当前正在发送的消息");
    await expect(composer).toBeDisabled();
    await page.getByRole("button", { name: "发起新聊天", exact: true }).click();
    await composer.fill("保留的新草稿");
    await pending[8].fulfill({ status: 500, json: { detail: { message: "旧请求失败" } } });
    await expect(composer).toHaveValue("保留的新草稿");
    await expect(composer).toBeEnabled();
    await expect(page.getByText("旧请求失败", { exact: true })).toHaveCount(0);
    await expect(page).toHaveURL(/\/$/);
    expect(errors).toEqual([]);
  });
}

for (const hasTouch of [false, true]) {
  test.describe(`checkbox pointer mode: ${hasTouch ? "touch" : "mouse"}`, () => {
    test.use({ hasTouch });
    test("chat selection uses the report filter checkbox colors and stays active when cleared", async ({ page }) => {
      await mockWorkspace(page, [model]);
      await page.route("**/api/conversations", route => route.fulfill({ json: { sessions: [{
        session_id: "existing", title: "已有聊天", member_id: "self", member_name: "本人", access_state: "available", is_pinned: false,
        created_at: "2026-09-07T00:00:00+08:00", last_active_at: "2026-09-07T00:00:00+08:00", pending_turn_status: null, queued_input_count: 0
      }], has_more: false, next_cursor: null } }));
      await page.goto("/health/self");
      await page.getByRole("button", { name: "按报告类型筛选", exact: true }).click();
      const reference = page.getByRole("option", { name: "检验报告", exact: true }).locator(".selection-check-control");
      const colors = await reference.evaluate(element => {
        const style = getComputedStyle(element);
        return [style.backgroundColor, style.borderColor, getComputedStyle(element.querySelector("svg")!).color];
      });
      await page.keyboard.press("Escape");
      await page.locator(".conversation-title-button").click({ button: "right" });
      await page.getByRole("menuitem", { name: "多选", exact: true }).click();
      const selected = page.locator(".conversation-selection-toggle");
      await expect(selected).toHaveAttribute("aria-pressed", "true");
      expect(await selected.evaluate(element => {
        const style = getComputedStyle(element, matchMedia("(pointer: coarse)").matches ? "::before" : null);
        return [style.backgroundColor, style.borderColor, getComputedStyle(element.querySelector("svg")!).color];
      })).toEqual(colors);
      if (hasTouch) expect(await selected.evaluate(element => getComputedStyle(element).backgroundColor)).toBe("rgba(0, 0, 0, 0)");
      await selected.click();
      await expect(selected).toHaveAttribute("aria-pressed", "false");
      await expect(page.getByRole("button", { name: "退出多选", exact: true })).toBeVisible();
    });

  });
}
