import { expect, test } from "@playwright/test";
import { mockWorkspace } from "../helpers/workspace";
import type { AddedModel } from "../../src/api/client";

test("editing a model publishes one catalog refresh to settings and the composer", async ({ page }) => {
  const profile = { availability: "available" as const, supports_text: true, file_mime_types: [], supports_tool_calling: true };
  let model: AddedModel = {
    model_id: "test:model", provider_id: "test", remote_model_id: "model", model_name: "原模型名称",
    thinking_modes: ["default"], supports_text: true, supports_tool_calling: true, file_mime_types: [],
    capability_profiles: { default_state: "non_thinking", non_thinking: profile, thinking: { ...profile, availability: "unavailable" } },
    context_window_tokens: 32000, max_output_tokens: 1024
  };
  await mockWorkspace(page, [model]);
  const counts = { models: 0, defaults: 0, writes: 0 };
  await page.route("**/api/model-providers", route => route.fulfill({ json: { providers: [
    { provider_id: "test", provider_name: "测试提供方", api_url: "https://test.invalid", official_url: "", has_api_key: true }
  ] } }));
  await page.route("**/api/models", route => { counts.models++; return route.fulfill({ json: { models: [model] } }); });
  await page.route("**/api/model-access-settings", route => {
    counts.defaults++;
    return route.fulfill({ json: { defaults: { chat: model, compact: model, title: model, vision_parse: model } } });
  });
  await page.route("**/api/models/test%3Amodel", route => {
    expect(route.request().method()).toBe("PATCH");
    expect(route.request().headers()["x-serenita-account-id"]).toBe("test");
    counts.writes++;
    model = { ...model, ...route.request().postDataJSON() };
    return route.fulfill({ json: model });
  });
  await page.goto("/setting");
  await page.getByRole("button", { name: "模型提供方", exact: true }).click();
  await page.getByRole("button", { name: "测试提供方", exact: true }).click();
  await page.getByRole("button", { name: "打开模型详情：model", exact: true }).click();
  const before = { ...counts };
  const input = page.getByLabel("模型名称", { exact: true });
  await input.fill("保存后的模型名称");
  await input.press("Tab");
  await expect.poll(() => counts.writes).toBe(1);
  await expect.poll(() => counts.defaults).toBe(before.defaults + 1);
  await expect(input).toHaveValue("保存后的模型名称");
  expect(counts.models).toBe(before.models + 1);
  await page.getByRole("button", { name: "发起新聊天", exact: true }).click();
  await expect(page.getByRole("button", { name: "模型与推理强度：保存后的模型名称，默认", exact: true })).toBeVisible();
  expect(counts.models).toBe(before.models + 1);
  expect(counts.defaults).toBe(before.defaults + 1);
});

test("a completed provider save preserves a newer URL draft and queues the latest write", async ({ page }) => {
  await mockWorkspace(page);
  const provider = { provider_id: "test", provider_name: "测试提供方", api_url: "https://initial.invalid", official_url: "https://official.invalid", has_api_key: false };
  const writes: string[] = [];
  const releases: (() => void)[] = [];
  await page.route("**/api/model-providers", async route => {
    if (route.request().method() === "GET") return route.fulfill({ json: { providers: [provider] } });
    const draft = route.request().postDataJSON();
    writes.push(draft.api_url);
    await new Promise<void>(resolve => releases.push(resolve));
    return route.fulfill({ json: { ...provider, ...draft } });
  });
  await page.goto("/setting");
  await page.getByRole("button", { name: "模型提供方", exact: true }).click();
  await page.getByRole("button", { name: "测试提供方", exact: true }).click();
  const input = page.getByLabel("API 地址", { exact: true });
  await input.fill("https://first.invalid");
  await expect.poll(() => writes).toEqual(["https://first.invalid"]);
  await input.fill("https://latest.invalid");
  releases[0]();
  await expect.poll(() => writes).toEqual(["https://first.invalid", "https://latest.invalid"]);
  await expect(input).toHaveValue("https://latest.invalid");
  const completed = page.waitForResponse(response => response.url().endsWith("/api/model-providers") && response.request().method() === "POST");
  releases[1](); await (await completed).finished();
  await expect(input).toHaveValue("https://latest.invalid");
});

test("revealing a saved web key cannot refill a draft edited and cleared during the request", async ({ page }) => {
  await mockWorkspace(page);
  await page.route("**/api/account-settings/web-access", route => route.fulfill({ json: {
    is_enabled: false, active_provider_id: "exa", providers: [{ provider_id: "exa", provider_name: "Exa", api_url: "https://exa.invalid", has_api_key: true }]
  } }));
  let release!: () => void;
  let requested = false;
  const gate = new Promise<void>(resolve => { release = resolve; });
  await page.route("**/api/account-settings/web-access/providers/exa/credential/reveal", async route => {
    requested = true; await gate;
    return route.fulfill({ json: { api_key: "test-secret" } });
  });
  await page.goto("/setting");
  await page.getByRole("button", { name: "联网工具", exact: true }).click();
  const reveal = page.getByRole("button", { name: "显示Exa API key", exact: true });
  await reveal.click(); await expect.poll(() => requested).toBe(true);
  const input = page.getByLabel("API key", { exact: true });
  await input.fill("new-draft"); await input.fill("");
  release(); await expect(reveal).toBeEnabled();
  await expect(input).toHaveValue(""); await expect(reveal).toHaveAttribute("aria-pressed", "false");
});

test("remote model picker fits a short viewport and returns keyboard focus to its opener", async ({ page }) => {
  await mockWorkspace(page);
  await page.route("**/api/model-providers", route => route.fulfill({ json: { providers: [
    { provider_id: "test", provider_name: "测试提供方", api_url: "https://test.invalid", official_url: "", has_api_key: true }
  ] } }));
  await page.route("**/api/model-providers/test/models", route => route.fulfill({ json: { models: [] } }));
  await page.goto("/setting");
  await page.getByRole("button", { name: "模型提供方", exact: true }).click();
  await page.getByRole("button", { name: "测试提供方", exact: true }).click();
  const opener = page.getByRole("button", { name: "添加模型", exact: true });
  await opener.click();
  await expect(page.getByText("暂无可添加模型。", { exact: true })).toBeVisible();
  await page.setViewportSize({ width: 300, height: 160 });
  const dialog = page.getByRole("dialog", { name: "添加模型", exact: true });
  await expect(dialog).toBeVisible();
  const bounds = (await dialog.boundingBox())!;
  expect(bounds.x).toBeGreaterThanOrEqual(0);
  expect(bounds.y).toBeGreaterThanOrEqual(0);
  expect(bounds.x + bounds.width).toBeLessThanOrEqual(300);
  expect(bounds.y + bounds.height).toBeLessThanOrEqual(160);
  await page.keyboard.press("Escape");
  await expect(dialog).toBeHidden();
  await expect(opener).toBeFocused();
});
