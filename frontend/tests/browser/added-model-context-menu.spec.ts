import { expect, test } from "@playwright/test";
import type { AddedModel } from "../../src/api/modelTypes";
import { mockWorkspace } from "../helpers/workspace";

for (const width of [1280, 390]) {
  test(`added models support context menu, selection and partial deletion at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 1000 });
    const profile = { availability: "available" as const, supports_text: true, file_mime_types: [], supports_tool_calling: true };
    let models: AddedModel[] = ["a", "b", "c"].map(id => ({
      model_id: `test:${id}`, provider_id: "test", remote_model_id: id, model_name: id,
      model_type: "generation", supports_text: true, file_mime_types: [], supports_tool_calling: true,
      thinking_modes: ["default"], capability_profiles: { default_state: "non_thinking", non_thinking: profile, thinking: { ...profile, availability: "unavailable" } },
      context_window_tokens: null, max_output_tokens: null, embedding_capabilities: null,
      embedding_dimensions: null, max_input_tokens: null, max_batch_size: null
    }));
    let failB = true;
    let chat: AddedModel | null = models[0];
    const deleted: string[] = [];
    await mockWorkspace(page, models);
    await page.route("**/api/model-providers", route => route.fulfill({ json: { providers: [{ provider_id: "test", provider_name: "测试提供方", api_url: "", official_url: "", has_api_key: false }] } }));
    await page.route("**/api/models", route => route.fulfill({ json: { models } }));
    await page.route("**/api/model-access-settings", route => route.fulfill({ json: { defaults: { chat, title: null, compact: null, vision_parse: null, text_embedding: null, multimodal_embedding: null } } }));
    await page.route("**/api/models/test%3A*", route => {
      expect(route.request().method()).toBe("DELETE");
      const id = decodeURIComponent(new URL(route.request().url()).pathname.split("/").at(-1)!);
      if (id === "test:b" && failB) return route.fulfill({ status: 503, json: { detail: { message: "暂时无法删除" } } });
      deleted.push(id); models = models.filter(model => model.model_id !== id);
      if (chat?.model_id === id) chat = null;
      return route.fulfill({ json: { model_id: id } });
    });
    const openProvider = async () => {
      await page.goto("/setting");
      await page.locator(".settings-nav").getByRole("button", { name: "模型提供方", exact: true }).click();
      await page.getByRole("button", { name: "测试提供方", exact: true }).click();
    };
    await openProvider();
    const rowA = page.getByRole("button", { name: "打开模型详情：a", exact: true });
    await rowA.click({ button: "right" });
    await expect(page.getByRole("menuitem", { name: "多选", exact: true })).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(rowA).toBeFocused();
    const originalTop = (await rowA.boundingBox())!.y;
    await rowA.press("Shift+F10");
    await page.getByRole("menuitem", { name: "多选", exact: true }).click();
    const selectedA = page.getByRole("checkbox", { name: "取消选择模型：a", exact: true });
    await expect(selectedA).toBeChecked();
    expect(Math.abs((await selectedA.boundingBox())!.y - originalTop)).toBeLessThan(1);
    await expect(page.getByRole("button", { name: "添加模型", exact: true })).toHaveCount(0);
    await page.getByRole("checkbox", { name: "选择模型：b", exact: true }).click();
    await page.getByRole("group", { name: "模型批量操作" }).getByRole("button", { name: "删除", exact: true }).click();
    await expect(page.getByRole("checkbox", { name: "取消选择模型：b", exact: true })).toBeChecked();
    await expect(page.getByRole("alert")).toContainText("暂时无法删除");
    expect(deleted).toEqual(["test:a"]); expect(chat).toBeNull();
    failB = false;
    await page.getByRole("group", { name: "模型批量操作" }).getByRole("button", { name: "删除", exact: true }).click();
    await expect(page.getByRole("button", { name: "打开模型详情：c", exact: true })).toBeVisible();
    await expect(page.getByRole("checkbox")).toHaveCount(0);

    const rowC = page.getByRole("button", { name: "打开模型详情：c", exact: true });
    const bounds = (await rowC.boundingBox())!;
    const cdp = await page.context().newCDPSession(page);
    await cdp.send("Input.dispatchTouchEvent", { type: "touchStart", touchPoints: [{ x: bounds.x + 30, y: bounds.y + bounds.height / 2 }] });
    await expect(page.getByRole("menuitem", { name: "多选", exact: true })).toBeVisible();
    await cdp.send("Input.dispatchTouchEvent", { type: "touchEnd", touchPoints: [] });
    await expect(page.getByRole("heading", { name: "已添加模型", exact: true })).toBeVisible();
    await page.getByRole("menuitem", { name: "多选", exact: true }).click();
    await page.keyboard.press("Escape");
    await expect(rowC).toBeVisible();
    await rowC.click({ button: "right" });
    await page.getByRole("menuitem", { name: "删除", exact: true }).click();
    await expect(page.getByText("暂未添加模型", { exact: true })).toBeVisible();
    expect(deleted).toEqual(["test:a", "test:b", "test:c"]);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  });
}
