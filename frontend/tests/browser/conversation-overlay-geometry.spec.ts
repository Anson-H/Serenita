import { expect, test, type Page } from "@playwright/test";

type ProductionHeightMode = "normal" | "compact" | "extreme";

type GeometryCase = {
  height: number;
  mode: ProductionHeightMode;
  reservedHeight: number;
};

const PRODUCTION_GEOMETRY_FIXTURE = "/tests/fixtures/conversation-overlay-geometry.html";

async function waitForStableProductionHeightMode(
  page: Page,
  expectedMode: ProductionHeightMode
) {
  await page.evaluate(async (mode) => {
    const deadline = performance.now() + 3_000;
    let stableFrames = 0;
    let lastMode = "unmounted";

    await new Promise<void>((resolve, reject) => {
      const sample = () => {
        const stage = document.querySelector<HTMLElement>(".home-workspace-content");
        if (stage) {
          const compact = stage.dataset.heightCompact === "true";
          const extreme = stage.dataset.heightExtreme === "true";
          lastMode = extreme ? "extreme" : compact ? "compact" : "normal";
          stableFrames = lastMode === mode ? stableFrames + 1 : 0;
        }
        if (stableFrames >= 8) {
          resolve();
          return;
        }
        if (performance.now() >= deadline) {
          reject(new Error(
            `Expected ${mode} for eight stable frames, last observed ${lastMode}.`
          ));
          return;
        }
        requestAnimationFrame(sample);
      };
      requestAnimationFrame(sample);
    });
  }, expectedMode);
}

async function arrangeProductionConversation(
  page: Page,
  options: {
    empty?: boolean;
    height: number;
    mode: ProductionHeightMode;
    width: number;
  }
) {
  await page.setViewportSize({ width: options.width, height: options.height });
  await page.goto(`${PRODUCTION_GEOMETRY_FIXTURE}${options.empty ? "?empty=1" : ""}`);
  const fixture = page.locator(".conversation-overlay-geometry-fixture");
  const workspace = fixture.locator(".home-workspace");
  const titlebar = workspace.locator(".workspace-titlebar");
  const stage = workspace.locator(".home-workspace-content");
  const composer = stage.locator(".conversation-composer");
  await expect(fixture).toBeVisible();
  await expect(composer).toBeVisible();
  await waitForStableProductionHeightMode(page, options.mode);
  return {
    composer,
    fixture,
    stage,
    tailButton: stage.getByRole("button", {
      name: "回到聊天最新内容并恢复自动跟随"
    }),
    titlebar
  };
}

test.beforeEach(async ({ page }) => {
  await page.route(url => url.pathname === "/api" || url.pathname.startsWith("/api/"), route => {
    void route.abort("blockedbyclient");
  });
});

for (const sample of [
  { height: 320, mode: "normal", reservedHeight: 96 },
  { height: 296, mode: "compact", reservedHeight: 96 },
  { height: 160, mode: "extreme", reservedHeight: 48 }
] satisfies GeometryCase[]) {
  test(`${sample.mode} floating composer preserves its ${sample.reservedHeight}px conversation region`, async ({ page }) => {
    const { composer, fixture, stage, tailButton } =
      await arrangeProductionConversation(page, {
        height: sample.height,
        mode: sample.mode,
        width: 390
      });
    const stageBox = (await stage.boundingBox())!;
    const composerBox = (await composer.boundingBox())!;

    expect(composerBox.y - stageBox.y).toBeGreaterThanOrEqual(sample.reservedHeight - 1);
    expect(composerBox.y + composerBox.height).toBeLessThanOrEqual(stageBox.y + stageBox.height + 1);

    const buttonBox = (await tailButton.boundingBox())!;
    expect(buttonBox.y).toBeGreaterThanOrEqual(stageBox.y);
    expect(buttonBox.y + buttonBox.height).toBeLessThanOrEqual(stageBox.y + stageBox.height);
    expect(composerBox.y - (buttonBox.y + buttonBox.height)).toBeGreaterThanOrEqual(8);

    const buttonOwnsHitPoint = await tailButton.evaluate(element => {
      const rect = element.getBoundingClientRect();
      const hit = document.elementFromPoint(rect.left + rect.width / 2, rect.top + rect.height / 2);
      return hit === element || element.contains(hit);
    });
    expect(buttonOwnsHitPoint).toBe(true);
    await tailButton.click();
    await expect(fixture).toHaveAttribute("data-tail-clicks", "1");
  });
}

test("compact composer returns to normal when the available height recovers", async ({ page }) => {
  await arrangeProductionConversation(page, { height: 296, mode: "compact", width: 390 });
  for (const height of [320, 296, 320]) {
    await page.setViewportSize({ width: 390, height });
    await waitForStableProductionHeightMode(page, height === 320 ? "normal" : "compact");
  }
  const composer = page.locator(".conversation-composer");
  await expect(composer).not.toHaveAttribute("data-height-compact", "true");
  await composer.getByRole("textbox", { name: "输入健康问题" }).fill("恢复后仍然可以输入");
  await waitForStableProductionHeightMode(page, "normal");
});

test("300x160 production workspace keeps extreme composer, tail control and tray reachable", async ({ page }) => {
  const { composer, fixture, stage, tailButton } =
    await arrangeProductionConversation(page, {
      height: 160,
      mode: "extreme",
      width: 300
    });
  const stageBox = (await stage.boundingBox())!;
  const composerBox = (await composer.boundingBox())!;

  const buttonBox = (await tailButton.boundingBox())!;
  expect(buttonBox.y).toBeGreaterThanOrEqual(stageBox.y);
  expect(buttonBox.y + buttonBox.height).toBeLessThanOrEqual(
    stageBox.y + stageBox.height
  );
  expect(composerBox.y - (buttonBox.y + buttonBox.height)).toBeGreaterThanOrEqual(8);

  const buttonOwnsHitPoint = await tailButton.evaluate((element) => {
    const rect = element.getBoundingClientRect();
    const hit = document.elementFromPoint(
      rect.left + rect.width / 2,
      rect.top + rect.height / 2
    );
    return hit === element || element.contains(hit);
  });
  expect(buttonOwnsHitPoint).toBe(true);
  await tailButton.click();
  await expect(fixture).toHaveAttribute("data-tail-clicks", "1");

  const details = composer.locator(".conversation-composer-auxiliary");
  const summary = details.locator(".conversation-composer-auxiliary-summary");
  await expect(details).not.toHaveAttribute("open", "");
  await expect(summary).toBeVisible();
  await expect(summary).toHaveCSS("width", "40px");
  await expect(summary).toHaveCSS("height", "40px");

  await summary.click();
  await expect(details).toHaveAttribute("open", "");
  const tray = details.locator(".conversation-composer-auxiliary-tray");
  await expect(tray).toBeVisible();
  const trayBox = (await tray.boundingBox())!;
  const visibleStage = {
    bottom: Math.min(stageBox.y + stageBox.height, 160),
    left: Math.max(stageBox.x, 0),
    right: Math.min(stageBox.x + stageBox.width, 300),
    top: Math.max(stageBox.y, 0)
  };
  expect(trayBox.y).toBeGreaterThanOrEqual(visibleStage.top);
  expect(trayBox.y + trayBox.height).toBeLessThanOrEqual(visibleStage.bottom);
  expect(trayBox.x).toBeGreaterThanOrEqual(visibleStage.left);
  expect(trayBox.x + trayBox.width).toBeLessThanOrEqual(visibleStage.right);

  const horizontalGeometry = await page.evaluate(() => {
    const stage = document.querySelector<HTMLElement>(".home-workspace-content")!;
    const composer = stage.querySelector<HTMLElement>(".conversation-composer")!;
    const textarea = composer.querySelector<HTMLTextAreaElement>("textarea")!;
    const surface = composer.querySelector<HTMLElement>(".conversation-composer-surface")!;
    const stageRect = stage.getBoundingClientRect();
    const composerRect = composer.getBoundingClientRect();
    const textareaRect = textarea.getBoundingClientRect();
    return {
      composerInsideStage:
        composerRect.left >= stageRect.left && composerRect.right <= stageRect.right,
      // The blurred backdrop intentionally spans the full column; measure editable content.
      surfaceOverflow: surface.scrollWidth - surface.clientWidth,
      documentOverflow: document.documentElement.scrollWidth - window.innerWidth,
      stageOverflow: stage.scrollWidth - stage.clientWidth,
      textareaInsideComposer:
        textareaRect.left >= composerRect.left && textareaRect.right <= composerRect.right,
      textareaWidth: textareaRect.width
    };
  });
  expect(horizontalGeometry).toMatchObject({
    composerInsideStage: true,
    surfaceOverflow: 0,
    documentOverflow: 0,
    stageOverflow: 0,
    textareaInsideComposer: true
  });
  expect(horizontalGeometry.textareaWidth).toBeGreaterThan(0);

  await page.keyboard.press("Escape");
  await expect(details).not.toHaveAttribute("open", "");
  await expect(summary).toBeFocused();
});

for (const viewport of [
  { height: 160, width: 300 },
  { height: 220, width: 390 }
]) {
  test(`empty conversation keeps its composer inside the stage at ${viewport.width}x${viewport.height}`, async ({ page }) => {
    const { composer, fixture, stage, titlebar } = await arrangeProductionConversation(page, {
      empty: true,
      height: viewport.height,
      mode: "extreme",
      width: viewport.width
    });
    await expect(fixture).toHaveAttribute("data-empty-conversation", "true");
      const stageBox = (await stage.boundingBox())!;
    const composerBox = (await composer.boundingBox())!;

    const titlebarBox = (await titlebar.boundingBox())!;
    expect(titlebarBox.y + titlebarBox.height).toBeLessThanOrEqual(stageBox.y);
    expect(composerBox.y).toBeGreaterThanOrEqual(stageBox.y);
    expect(composerBox.y + composerBox.height).toBeLessThanOrEqual(
      stageBox.y + stageBox.height
    );
    expect(await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth))
      .toBe(0);

    const textarea = composer.getByRole("textbox", { name: "输入健康问题" });
    await textarea.click();
    await expect(textarea).toBeFocused();
  });
}

for (const sample of [
  { availableBudget: 64, mode: "extreme", stageHeight: 190, viewportHeight: 240 },
  { availableBudget: 109, mode: "extreme", stageHeight: 235, viewportHeight: 285 },
  { availableBudget: 110, mode: "extreme", stageHeight: 236, viewportHeight: 286 },
  { availableBudget: 120, mode: "compact", stageHeight: 246, viewportHeight: 296 }
] satisfies Array<{
  availableBudget: number;
  mode: ProductionHeightMode;
  stageHeight: number;
  viewportHeight: number;
}>) {
  test(`production auxiliary remains reachable at ${sample.availableBudget}px available budget`, async ({ page }) => {
    const { composer, fixture, stage } = await arrangeProductionConversation(page, {
      height: sample.viewportHeight,
      mode: sample.mode,
      width: 300
    });
    const stageBox = (await stage.boundingBox())!;
    expect(stageBox.height).toBe(sample.stageHeight);

    const details = composer.locator(".conversation-composer-auxiliary");
    const summary = details.locator(".conversation-composer-auxiliary-summary");
    if (sample.mode === "extreme") {
      await expect(details).not.toHaveAttribute("open", "");
      await expect(summary).toBeVisible();
      await summary.click();
      await expect(details).toHaveAttribute("open", "");
    } else {
      await expect(details).toHaveAttribute("open", "");
      await expect(summary).toBeHidden();
    }

    const tray = details.locator(".conversation-composer-auxiliary-tray");
    await expect(tray).toBeVisible();
    const trayGeometry = await tray.evaluate((element) => ({
      clientHeight: element.clientHeight,
      scrollHeight: element.scrollHeight
    }));
    expect(trayGeometry.clientHeight).toBeGreaterThan(0);
    expect(trayGeometry.scrollHeight).toBeGreaterThan(trayGeometry.clientHeight);

    const runNow = tray.getByRole("button", { name: "调整方向" }).last();
    await runNow.scrollIntoViewIfNeeded();
    const actionOwnsHitPoint = await runNow.evaluate((element) => {
      const rect = element.getBoundingClientRect();
      const hit = document.elementFromPoint(
        rect.left + rect.width / 2,
        rect.top + rect.height / 2
      );
      return hit === element || element.contains(hit);
    });
    expect(actionOwnsHitPoint).toBe(true);
    await runNow.click();
    await expect(fixture).toHaveAttribute("data-queue-action-clicks", "1");
  });
}

for (const width of [390, 1280]) {
  test(`report composer floats and thinking choices remain reachable at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 740 });
    await page.goto(`${PRODUCTION_GEOMETRY_FIXTURE}?report=1&empty=1`);
    const composer = page.locator(".conversation-composer");
    await expect(composer).toHaveCSS("position", "absolute");
    const expectedWidth = await page.locator(".report-detail-pane").evaluate(node => {
      const gap = Number.parseFloat(getComputedStyle(node).getPropertyValue("--space-content"));
      return Math.min(750, node.clientWidth - gap * 2);
    });
    await expect.poll(async () => (await composer.boundingBox())!.width).toBeCloseTo(expectedWidth, 0);
    await page.getByRole("button", { name: /模型与推理强度/ }).click();
    const slider = page.getByRole("slider", { name: "推理强度" });
    await expect(slider).toBeInViewport({ ratio: 0.98 });
    await slider.focus();
    await slider.press("ArrowRight");
    await expect(slider).toHaveAttribute("aria-valuetext", "high");
    await expect(page.locator(".composer-reasoning-value")).toHaveText("high");
    await slider.press("Home");
    await expect(slider).toHaveAttribute("aria-valuetext", "low");
    await page.getByRole("button", { name: "选择模型：测试模型" }).click();
    await expect(page.getByText("未添加聊天模型", { exact: true })).toBeVisible();
    await page.getByRole("button", { name: /模型与推理强度/ }).click();
    await page.locator(".report-detail-scroll").evaluate(node => { node.scrollTop = node.scrollHeight; });
    const end = await page.getByRole("button", { name: "报告末尾" }).boundingBox();
    const box = await composer.boundingBox();
    expect(end!.y + end!.height).toBeLessThanOrEqual(box!.y);
    expect(box!.y + box!.height).toBeLessThan(740);
  });
}
