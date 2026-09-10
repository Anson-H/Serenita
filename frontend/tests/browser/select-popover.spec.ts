import { mockWorkspace } from "../helpers/workspace";
import { expect, test, type Locator } from "@playwright/test";
import type {
  AddedModel,
  ModelModeCapabilityProfile,
} from "../../src/api/types";

const profile: ModelModeCapabilityProfile = {
  availability: "available",
  supports_text: true,
  file_mime_types: ["image/png"],
  supports_tool_calling: true,
};

const longModel = "deepseek-v4-flash-vision-exp";

const models: AddedModel[] = ["qwen3.8-flash", longModel].map((name) => ({
  model_id: name,
  remote_model_id: name,
  model_name: name,
  provider_id: "deepseek",
  supports_text: true,
  supports_tool_calling: true,
  file_mime_types: ["image/png"],
  model_type: "generation", embedding_capabilities: null, embedding_dimensions: null, max_input_tokens: null, max_batch_size: null, thinking_modes: ["non_thinking"],
  capability_profiles: {
    default_state: "non_thinking",
    non_thinking: profile,
    thinking: profile,
  },
  context_window_tokens: 32000,
  max_output_tokens: 8000,
}));

async function box(locator: Locator) {
  const bounds = await locator.boundingBox();
  expect(bounds).not.toBeNull();
  return bounds!;
}

for (const width of [1280, 390]) {
  test(`model menu aligns right and recovers content width at ${width}px`, async ({
    page,
  }) => {
    await mockWorkspace(page, models);
    await page.setViewportSize({ width, height: 900 });
    await page.goto("/setting");
    await page.getByRole("button", { name: "默认模型", exact: true }).click();
    const trigger = page.getByRole("button", {
      name: "设置聊天模型",
      exact: true,
    });
    await expect(trigger).toContainText("qwen3.8-flash");
    await trigger.focus();
    await page.keyboard.press("ArrowDown");
    const menu = page.getByRole("listbox");
    await expect(
      page.getByRole("option", { name: longModel, exact: true }),
    ).toBeVisible();
    await expect
      .poll(async () => {
        const t = await box(trigger),
          m = await box(menu);
        return Math.abs(m.x + m.width - t.x - t.width);
      })
      .toBeLessThan(1);
    const originalWidth = (await box(menu)).width;
    await expect(menu.getByRole("option", { selected: true })).toBeFocused();
    await page.keyboard.press("End");
    await expect(menu.getByRole("option").last()).toBeFocused();
    await page.keyboard.press("Home");
    await expect(menu.getByRole("option").first()).toBeFocused();
    await page.setViewportSize({ width: 240, height: 900 });
    await expect
      .poll(async () => (await box(menu)).width)
      .toBeLessThanOrEqual(210);
    await page.setViewportSize({ width, height: 900 });
    await expect
      .poll(async () => Math.abs((await box(menu)).width - originalWidth))
      .toBeLessThan(1);
    await page.keyboard.press("Escape");
    await expect(menu).toHaveCount(0);
    await expect(trigger).toBeFocused();
  });

  test(`report filter matches its trigger and stays open after selection at ${width}px`, async ({
    page,
  }) => {
    await mockWorkspace(page, models);
    await page.setViewportSize({ width, height: 900 });
    await page.goto("/reports");
    const trigger = page.getByRole("button", {
      name: "按医疗报告类型筛选",
      exact: true,
    });
    await trigger.click();
    const menu = page.getByRole("listbox");
    await expect(menu).toBeVisible();
    const checkWidth = async () => {
      const t = await box(trigger),
        m = await box(menu);
      return Math.max(Math.abs(t.width - m.width), Math.abs(t.x - m.x));
    };
    await expect.poll(checkWidth).toBeLessThan(1);
    const option = page.getByRole("option", { name: "检验报告", exact: true });
    await option.locator(".selection-check-icon").click();
    await expect(option).toHaveAttribute("aria-selected", "false");
    await expect(menu).toBeVisible();
    await option.locator(".selection-check-control").click();
    await expect(option).toHaveAttribute("aria-selected", "true");
    await expect(menu).toBeVisible();
    const bounds = await box(option);
    await option.click({
      position: { x: bounds.width - 5, y: bounds.height / 2 },
    });
    await expect(option).toHaveAttribute("aria-selected", "false");
    await expect(menu).toBeVisible();
    await page.setViewportSize({
      width: width === 390 ? 1280 : 390,
      height: 900,
    });
    await expect.poll(checkWidth).toBeLessThan(1);
    await page.keyboard.press("Escape");
    await expect(trigger).toBeFocused();
  });
}

test.describe("completed touch selection", () => {
  test.use({ hasTouch: true, viewport: { width: 390, height: 420 } });

  for (const multiple of [false, true]) {
    test(`${multiple ? "multiple" : "single"} selection ignores a real scrolling gesture`, async ({
      page,
      context,
    }) => {
      const many = Array.from({ length: 32 }, (_, index) => ({
        ...models[0],
        model_id: `m${index}`,
        remote_model_id: `m${index}`,
        model_name: `模型 ${index}`,
      }));
      await mockWorkspace(page, many);
      await page.goto(multiple ? "/reports" : "/setting");
      if (!multiple)
        await page
          .getByRole("button", { name: "默认模型", exact: true })
          .click();
      const trigger = page.getByRole("button", {
        name: multiple ? "按医疗报告类型筛选" : "设置聊天模型",
        exact: true,
      });
      await trigger.tap();
      const menu = page.getByRole("listbox");
      await expect(menu).toBeVisible();
      const before = await menu
        .getByRole("option")
        .evaluateAll((items) =>
          items.map((item) => item.getAttribute("aria-selected")),
        );
      const bounds = await box(menu);
      const x = bounds.x + bounds.width / 2;
      const startY = bounds.y + bounds.height - 20;
      const cdp = await context.newCDPSession(page);
      await cdp.send("Input.dispatchTouchEvent", {
        type: "touchStart",
        touchPoints: [{ x, y: startY }],
      });
      for (let step = 1; step <= 8; step++) {
        await cdp.send("Input.dispatchTouchEvent", {
          type: "touchMove",
          touchPoints: [{ x, y: startY - step * 12 }],
        });
        await page.waitForTimeout(20);
      }
      await cdp.send("Input.dispatchTouchEvent", {
        type: "touchEnd",
        touchPoints: [],
      });
      await expect(menu).toBeVisible();
      await expect
        .poll(() =>
          menu
            .getByRole("option")
            .evaluateAll((items) =>
              items.map((item) => item.getAttribute("aria-selected")),
            ),
        )
        .toEqual(before);
      await expect
        .poll(() => menu.evaluate((element) => element.scrollTop))
        .toBeGreaterThan(0);
      const option = menu.getByRole("option").last();
      const selected = await option.getAttribute("aria-selected");
      await option.tap();
      if (multiple)
        await expect(option).toHaveAttribute(
          "aria-selected",
          selected === "true" ? "false" : "true",
        );
      else await expect(menu).toHaveCount(0);
    });
  }
});
