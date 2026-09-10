import { expect, test } from "@playwright/test";
import { mockWorkspace } from "../helpers/workspace";
import type { AddedModel, ModelDefaults } from "../../src/api/modelTypes";
import { eligibleForDefault } from "../../src/features/modelConfiguration/modelEligibility";

function fixtures(): AddedModel[] {
  const profile = { availability: "available" as const, supports_text: true, file_mime_types: ["image/png"], supports_tool_calling: true };
  const base: AddedModel = { model_id: "test:chat", provider_id: "test", remote_model_id: "chat", model_name: "生成示例", model_type: "generation", thinking_modes: ["default"], capability_profiles: { default_state: "non_thinking", non_thinking: profile, thinking: { ...profile, availability: "unavailable" } }, context_window_tokens: 32000, max_output_tokens: 2000, supports_text: true, file_mime_types: ["image/png"], supports_tool_calling: true, embedding_capabilities: null, embedding_dimensions: null, max_input_tokens: null, max_batch_size: null };
  const embedding: AddedModel = { ...base, model_id: "test:embedding", remote_model_id: "embedding", model_name: "多模态示例", model_type: "embedding", embedding_dimensions: 1024, thinking_modes: null, capability_profiles: null, supports_text: false, supports_tool_calling: false, file_mime_types: [], context_window_tokens: null, max_output_tokens: null, embedding_capabilities: { supports_text: true, file_mime_types: ["image/png"], independent: "supported", fusion: "supported", dimensions: { "512": "supported" }, protocol: "compatible" } };
  return [base, embedding, { ...embedding, model_id: "test:unknown", remote_model_id: "unknown", model_name: "未确认示例", model_type: "unknown", embedding_capabilities: null }];
}

for (const width of [1280, 390]) {
  test(`embedding editing, defaults, refresh and cancellation at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 1000 });
    let models = fixtures();
    let defaults: ModelDefaults = { chat: models[0], title: null, compact: null, vision_parse: null, text_embedding: null, multimodal_embedding: null };
    await mockWorkspace(page, models);
    await page.route("**/api/model-providers", route => route.fulfill({ json: { providers: [{ provider_id: "test", provider_name: "测试提供方", api_url: "https://test.invalid/v1", official_url: "", is_configured: true, has_api_key: true, native_attachment_mime_types: ["image/png"] }] } }));
    await page.route("**/api/models", route => route.fulfill({ json: { models } }));
    await page.route("**/api/model-access-settings", route => {
      if (route.request().method() === "PATCH") for (const [purpose, id] of Object.entries(route.request().postDataJSON())) {
        const key = purpose as keyof ModelDefaults;
        const model = models.find(model => model.model_id === id) ?? null;
        expect(!model || eligibleForDefault(model, key)).toBeTruthy();
        defaults = { ...defaults, [key]: model };
      }
      return route.fulfill({ json: { defaults } });
    });
    let failSave = false;
    await page.route("**/api/models/test%3A*", route => {
      if (failSave) return route.fulfill({ status: 503, json: { detail: { message: "保存暂时失败" } } });
      const id = decodeURIComponent(new URL(route.request().url()).pathname.split("/").at(-1)!);
      const patch = route.request().postDataJSON();
      models = models.map(model => model.model_id === id ? { ...model, ...patch } : model);
      for (const key of Object.keys(defaults) as (keyof ModelDefaults)[]) {
        const selected = models.find(model => model.model_id === defaults[key]?.model_id);
        defaults[key] = selected && eligibleForDefault(selected, key) ? selected : null;
      }
      return route.fulfill({ json: models.find(model => model.model_id === id) });
    });
    let release!: () => void;
    let cancelled = false;
    await page.route("**/api/models/capability-probe/test%3A*", async route => {
      await new Promise<void>(resolve => { release = resolve; });
      await route.fulfill({ status: 409, json: { detail: { message: "模型模型检测已停止。" } } });
    });
    await page.route("**/api/models/capability-probe-cancel/test%3A*", async route => {
      expect(route.request().postDataJSON().probe_id).toBeTruthy();
      cancelled = true; release(); await route.fulfill({ json: { cancelled: true } });
    });
    const openDefaults = async () => { await page.goto("/setting"); await page.locator(".settings-nav").getByRole("button", { name: "默认模型", exact: true }).click(); };
    await openDefaults();
    await expect(page.getByRole("heading", { name: "生成模型", exact: true })).toBeVisible();
    await expect(page.getByRole("heading", { name: "向量模型", exact: true })).toBeVisible();
    await page.getByRole("button", { name: "设置文本向量模型", exact: true }).click();
    await expect(page.getByRole("option", { name: "多模态示例", exact: true })).toBeVisible();
    await expect(page.getByRole("option", { name: "生成示例", exact: true })).toHaveCount(0);
    await expect(page.getByRole("option", { name: "未确认示例", exact: true })).toHaveCount(0);
    await page.getByRole("option", { name: "多模态示例", exact: true }).click();
    await expect.poll(() => defaults.text_embedding?.model_id).toBe("test:embedding");
    const openModel = async (id: string) => { await page.goto("/setting"); await page.locator(".settings-nav").getByRole("button", { name: "模型提供方", exact: true }).click(); await page.getByRole("button", { name: "测试提供方", exact: true }).click(); await page.getByRole("button", { name: `打开模型详情：${id}`, exact: true }).click(); };
    await openModel("embedding");
    await expect(page.locator('[aria-label="能力设置"] > :first-child')).toContainText("模型类型");
    await page.getByRole("button", { name: /^输入与输出/ }).click();
    await expect(page.getByRole("heading", { name: "输入与输出", exact: true })).toBeVisible();
    await expect(page.getByRole("heading", { name: "输入模态", exact: true })).toBeVisible();
    await expect(page.getByRole("heading", { name: "输出格式", exact: true })).toBeVisible();
    await expect(page.getByText("独立向量", { exact: true })).toBeVisible();
    await expect(page.getByText("融合向量", { exact: true })).toBeVisible();
    await expect(page.getByText("默认输出维度", { exact: true })).toHaveCount(0);
    const dimensions = page.getByLabel("输出维度", { exact: true });
    await expect(dimensions).toHaveValue("1024");
    await dimensions.fill("512"); await dimensions.press("Tab");
    await expect.poll(() => models[1].embedding_dimensions).toBe(512);
    await openModel("embedding");
    await page.getByRole("button", { name: /^输入与输出/ }).click();
    await expect(page.getByLabel("输出维度", { exact: true })).toHaveValue("512");
    await openModel("embedding");
    await page.locator(".model-capability-navigation-row").filter({ hasText: "输入与输出" }).click();
    await expect(page.getByRole("heading", { name: "输入模态", exact: true })).toBeVisible();
    const audio = page.getByRole("button", { name: "音频", exact: true });
    await expect(audio).toHaveAttribute("aria-pressed", "false");
    await audio.click();
    await expect(audio).toHaveAttribute("aria-pressed", "true");
    expect(models[1].embedding_capabilities?.file_mime_types).toContain("audio/mpeg");
    await page.getByRole("button", { name: "详细自定义", exact: true }).click();
    const formats = page.getByRole("textbox", { name: "精确编辑 MIME 类型" });
    await formats.fill("image/webp\naudio/wav\napplication/pdf");
    failSave = true;
    await page.getByRole("dialog").getByRole("button", { name: "完成", exact: true }).click();
    await expect(page.getByRole("dialog").getByRole("alert")).toContainText("保存暂时失败");
    await expect(formats).toHaveValue("image/webp\naudio/wav\napplication/pdf");
    failSave = false;
    await page.getByRole("dialog").getByRole("button", { name: "完成", exact: true }).click();
    await expect(page.getByRole("dialog")).toHaveCount(0);
    await expect.poll(() => models[1].embedding_capabilities?.file_mime_types).toEqual(["image/webp", "audio/wav", "application/pdf"]);
    await page.getByRole("button", { name: "文本", exact: true }).click();
    await expect.poll(() => models[1].embedding_capabilities?.supports_text).toBe(false);
    await page.locator(".model-settings-panel-body").screenshot({ path: `../artifacts/verification/embedding-input-output-${width}.png` });
    await openModel("chat");
    await page.getByRole("button", { name: /^输入与输出/ }).click();
    await expect(page.getByRole("heading", { name: "输入与输出", exact: true })).toBeVisible();
    await expect(page.getByRole("heading", { name: "输入模态", exact: true })).toBeVisible();
    await expect(page.getByRole("heading", { name: "输出格式", exact: true })).toBeVisible();
    await page.locator(".model-input-options").getByRole("button", { name: "图片", exact: true }).click();
    await expect.poll(() => models[0].capability_profiles?.non_thinking.file_mime_types).toEqual([]);
    await page.locator(".model-output-options").getByRole("button", { name: "工具调用", exact: true }).click();
    await expect.poll(() => models[0].capability_profiles?.non_thinking.supports_tool_calling).toBe(false);
    await page.locator(".model-settings-panel-body").screenshot({ path: `../artifacts/verification/generation-input-output-${width}.png` });
    await openModel("embedding");
    await expect(page.getByRole("button", { name: "思考", exact: true })).toHaveCount(0);
    await expect(page.getByText("批量输入", { exact: true })).toHaveCount(0);
    const batchLimit = page.getByLabel("批量输入上限", { exact: true });
    await batchLimit.fill("1"); await batchLimit.press("Tab");
    await expect.poll(() => models[1].max_batch_size).toBe(1);
    const limit = page.getByLabel("单条输入词元上限", { exact: true });
    await limit.fill("4096"); await limit.press("Tab");
    await expect.poll(() => models[1].max_input_tokens).toBe(4096);
    await openModel("embedding"); await expect(limit).toHaveValue("4096");
    failSave = true;
    await limit.fill("8192"); await limit.press("Tab");
    await expect(page.getByRole("alert")).toContainText("保存暂时失败");
    await expect(limit).toHaveValue("8192");
    failSave = false;
    await limit.focus(); await limit.press("Tab");
    await expect.poll(() => models[1].max_input_tokens).toBe(8192);
    await page.getByRole("button", { name: "检测模型", exact: true }).click();
    await page.getByRole("button", { name: "检测中", exact: true }).click();
    await expect.poll(() => cancelled).toBeTruthy();
    await expect(page.getByRole("button", { name: "取消检测", exact: true })).toHaveCount(0);
    await expect(limit).toHaveValue("8192");
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
    await page.screenshot({ path: `../artifacts/verification/embedding-model-${width}.png`, fullPage: true });
    await openDefaults();
    await expect(page.getByRole("button", { name: "设置文本向量模型", exact: true })).toContainText("不设置");
    await page.screenshot({ path: `../artifacts/verification/embedding-defaults-${width}.png`, fullPage: true });
    for (const id of ["chat", "unknown"]) {
      await openModel(id);
      cancelled = false;
      await page.getByRole("button", { name: "检测模型", exact: true }).click();
      await expect(page.getByRole("button", { name: "取消检测", exact: true })).toHaveCount(0);
      await page.getByRole("button", { name: "检测中", exact: true }).click();
      await expect.poll(() => cancelled).toBeTruthy();
      await expect(page.getByRole("button", { name: "检测模型", exact: true })).toBeEnabled();
    }
    await openModel("unknown");
    await page.getByRole("button", { name: "模型类型", exact: true }).click();
    await page.getByRole("option", { name: "向量模型", exact: true }).click();
    await expect(page.getByRole("heading", { name: "输入限制", exact: true })).toBeVisible();
    await expect.poll(() => models[2].model_type).toBe("embedding");
  });
}
