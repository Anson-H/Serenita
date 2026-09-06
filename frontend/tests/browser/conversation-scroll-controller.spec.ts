import { expect, test, type Locator, type Page } from "@playwright/test";

const FIXTURE_PATH = "/tests/fixtures/conversation-scroll-controller.html";

async function tailDistance(surface: Locator) {
  return surface.evaluate(element =>
    Math.max(0, element.scrollHeight - element.clientHeight - element.scrollTop));
}

async function waitForStableTail(fixture: Locator, surface: Locator) {
  await expect(fixture).toHaveAttribute("data-follow-intent", "following");
  await expect(fixture).toHaveAttribute("data-operation", "idle");
  await expect.poll(() => tailDistance(surface)).toBeLessThanOrEqual(1);
}

async function firstVisibleMessage(surface: Locator) {
  return surface.evaluate(element => {
    const surfaceRect = element.getBoundingClientRect();
    const candidates = [...element.querySelectorAll<HTMLElement>("[data-message-id]")]
      .map(node => ({ id: node.dataset.messageId!, top: node.getBoundingClientRect().top,
        bottom: node.getBoundingClientRect().bottom }))
      .filter(candidate => candidate.bottom > surfaceRect.top + 1 && candidate.top < surfaceRect.bottom - 1)
      .sort((left, right) => left.top - right.top);
    if (!candidates[0]) throw new Error("No visible message was found.");
    return candidates[0];
  });
}

async function messageCenterOffset(page: Page, messageId: string) {
  return page.evaluate(id => {
    const surface = document.querySelector<HTMLElement>(".conversation-surface")!;
    const stage = document.querySelector<HTMLElement>(".home-workspace-content")!;
    const message = document.querySelector<HTMLElement>(`[data-message-id="${id}"]`)!;
    const surfaceRect = surface.getBoundingClientRect();
    const stageRect = stage.getBoundingClientRect();
    const messageRect = message.getBoundingClientRect();
    const overlayHeight = Number.parseFloat(
      getComputedStyle(stage).getPropertyValue("--composer-overlay-height")
    );
    const composerTop = stage.querySelector<HTMLElement>(".conversation-composer")
      ?.getBoundingClientRect().top ?? surfaceRect.bottom;
    const returnButtonTop = stage.querySelector<HTMLElement>(".conversation-tail-button")
      ?.getBoundingClientRect().top ?? surfaceRect.bottom;
    const readableBottom = Math.min(
      surfaceRect.bottom,
      composerTop,
      returnButtonTop,
      Number.isFinite(overlayHeight)
        ? stageRect.bottom - overlayHeight
        : surfaceRect.bottom
    );
    return messageRect.top + messageRect.height / 2 -
      (surfaceRect.top + (readableBottom - surfaceRect.top) / 2);
  }, messageId);
}

test.beforeEach(async ({ page }) => {
  await page.route(url => url.pathname === "/api" || url.pathname.startsWith("/api/"), route => {
    void route.abort("blockedbyclient");
  });
  await page.setViewportSize({ width: 900, height: 700 });
  await page.goto(FIXTURE_PATH);
  const fixture = page.getByTestId("conversation-scroll-fixture");
  const surface = page.getByRole("region", { name: "当前聊天内容", exact: true });
  await expect(fixture).toBeVisible();
  await waitForStableTail(fixture, surface);
});

test("second-round shrink then grow stays at the production controller tail", async ({ page }) => {
  const fixture = page.getByTestId("conversation-scroll-fixture");
  const surface = page.getByRole("region", { name: "当前聊天内容", exact: true });
  const initialScrollHeight = await surface.evaluate(element => element.scrollHeight);

  await page.getByRole("button", { name: "开始第二轮", exact: true }).click();
  await expect(fixture).toHaveAttribute("data-phase", "second-round-grown");
  const shrinkHeight = Number(await fixture.getAttribute("data-shrink-height"));
  expect(shrinkHeight).toBeLessThan(initialScrollHeight);
  expect(await surface.evaluate(element => element.scrollHeight)).toBeGreaterThan(shrinkHeight);
  await waitForStableTail(fixture, surface);
  await page.waitForTimeout(100);
  expect(await tailDistance(surface)).toBeLessThanOrEqual(1);
});

test("async media growth keeps a follower at the exact tail", async ({ page }) => {
  const fixture = page.getByTestId("conversation-scroll-fixture");
  const surface = page.getByRole("region", { name: "当前聊天内容", exact: true });
  const initialScrollHeight = await surface.evaluate(element => element.scrollHeight);

  await page.getByRole("button", { name: "异步内容增长", exact: true }).click();
  await expect(fixture).toHaveAttribute("data-media-height", "360");
  await expect.poll(() => surface.evaluate(element => element.scrollHeight))
    .toBeGreaterThan(initialScrollHeight + 250);
  await waitForStableTail(fixture, surface);
  await page.waitForTimeout(100);
  expect(await tailDistance(surface)).toBeLessThanOrEqual(1);
});

test("paused reading preserves the first visible message while content is prepended", async ({ page }) => {
  const fixture = page.getByTestId("conversation-scroll-fixture");
  const surface = page.getByRole("region", { name: "当前聊天内容", exact: true });
  await surface.hover();
  await page.mouse.wheel(0, -520);
  await expect(fixture).toHaveAttribute("data-follow-intent", "paused");
  await page.waitForTimeout(180);
  const anchorBefore = await firstVisibleMessage(surface);

  await page.getByRole("button", { name: "在上方增加内容", exact: true }).click();
  await expect(fixture).toHaveAttribute("data-prepend-count", "1");
  await expect(fixture).toHaveAttribute("data-operation", "idle");
  const anchor = page.locator(`[data-message-id="${anchorBefore.id}"]`);
  await expect.poll(async () => (await anchor.boundingBox())?.y ?? Number.NaN)
    .toBeCloseTo(anchorBefore.top, 0);
  await page.waitForTimeout(100);
  expect((await anchor.boundingBox())!.y).toBeCloseTo(anchorBefore.top, 0);
  await expect(fixture).toHaveAttribute("data-follow-intent", "paused");
});

test("a source request centers once and returnToLatest finishes at the tail with focus", async ({ page }) => {
  const fixture = page.getByTestId("conversation-scroll-fixture");
  const surface = page.getByRole("region", { name: "当前聊天内容", exact: true });
  const sourceId = "fixture-message-9";

  await page.getByRole("button", { name: "定位来源", exact: true }).click();
  await expect(fixture).toHaveAttribute("data-follow-intent", "paused");
  await expect(fixture).toHaveAttribute("data-operation", "idle");
  await expect.poll(async () => Math.abs(await messageCenterOffset(page, sourceId)))
    .toBeLessThanOrEqual(1);

  await surface.hover();
  await page.mouse.wheel(0, -220);
  await page.waitForTimeout(180);
  const offsetAfterReading = await messageCenterOffset(page, sourceId);
  expect(Math.abs(offsetAfterReading)).toBeGreaterThan(100);

  await page.getByRole("button", { name: "保持来源请求并追加消息", exact: true }).click();
  await expect(fixture).toHaveAttribute("data-append-count", "1");
  await expect(fixture).toHaveAttribute("data-operation", "idle");
  await expect.poll(() => messageCenterOffset(page, sourceId)).toBeCloseTo(offsetAfterReading, 0);
  expect(Math.abs(await messageCenterOffset(page, sourceId))).toBeGreaterThan(100);

  const returnButton = page.getByRole("button", {
    name: "回到聊天最新内容并恢复自动跟随",
    exact: true
  });
  await expect(returnButton).toBeVisible();
  await returnButton.focus();
  await expect(returnButton).toBeFocused();
  await returnButton.press("Enter");
  await expect(returnButton).toHaveCount(0);
  await waitForStableTail(fixture, surface);
  await expect(surface).toBeFocused();
  await page.waitForTimeout(100);
  expect(await tailDistance(surface)).toBeLessThanOrEqual(1);
});

test("1000-turn conversation keeps source location and tail return responsive", async ({ page }) => {
  const fixture = page.getByTestId("conversation-scroll-fixture");
  const surface = page.getByRole("region", { name: "当前聊天内容", exact: true });

  await page.getByRole("button", { name: "加载1000轮", exact: true }).click();
  await expect(fixture).toHaveAttribute("data-message-count", "1000");
  await waitForStableTail(fixture, surface);

  await surface.hover();
  await page.mouse.wheel(0, -720);
  await expect(fixture).toHaveAttribute("data-follow-intent", "paused");
  await page.waitForTimeout(180);
  const longConversationAnchor = await firstVisibleMessage(surface);
  await page.getByRole("button", { name: "在上方增加内容", exact: true }).click();
  await expect(fixture).toHaveAttribute("data-operation", "idle");
  const preservedAnchor = page.locator(
    `[data-message-id="${longConversationAnchor.id}"]`
  );
  await expect.poll(async () => (await preservedAnchor.boundingBox())?.y ?? Number.NaN)
    .toBeCloseTo(longConversationAnchor.top, 0);

  await page.getByRole("button", { name: "定位长对话来源", exact: true }).click();
  await expect(fixture).toHaveAttribute("data-follow-intent", "paused");
  await expect(fixture).toHaveAttribute("data-operation", "idle");
  await expect.poll(async () => Math.abs(await messageCenterOffset(page, "fixture-message-500")))
    .toBeLessThanOrEqual(1);

  await page.getByRole("button", {
    name: "回到聊天最新内容并恢复自动跟随",
    exact: true
  }).click();
  await waitForStableTail(fixture, surface);
  expect(await tailDistance(surface)).toBeLessThanOrEqual(1);
});

test("all non-return transitions transfer tail-button focus before hiding it", async ({ page }) => {
  const fixture = page.getByTestId("conversation-scroll-fixture");
  const surface = page.getByRole("region", { name: "当前聊天内容", exact: true });
  await surface.hover();
  await page.mouse.wheel(0, -520);
  await expect(fixture).toHaveAttribute("data-follow-intent", "paused");

  const returnButton = page.getByRole("button", {
    name: "回到聊天最新内容并恢复自动跟随",
    exact: true
  });
  await returnButton.focus();
  await expect(returnButton).toBeFocused();
  await page.getByRole("button", { name: "强制跟随", exact: true }).evaluate((button) => {
    (button as HTMLButtonElement).click();
  });

  await expect(returnButton).toHaveCount(0);
  await expect(surface).toBeFocused();
  await waitForStableTail(fixture, surface);
});

test("a stalled forced return exposes a retry after the two-second boundary", async ({ page }) => {
  const fixture = page.getByTestId("conversation-scroll-fixture");
  const surface = page.getByRole("region", { name: "当前聊天内容", exact: true });
  await surface.hover();
  await page.mouse.wheel(0, -520);
  await expect(fixture).toHaveAttribute("data-follow-intent", "paused");

  await surface.evaluate((element) => {
    const scrollSurface = element as HTMLElement;
    const originalScrollTo = scrollSurface.scrollTo;
    scrollSurface.scrollTo = () => undefined;
    (window as unknown as { restoreFixtureScroll?: () => void }).restoreFixtureScroll = () => {
      scrollSurface.scrollTo = originalScrollTo;
    };
  });
  await page.getByRole("button", { name: "强制跟随", exact: true }).evaluate((button) => {
    (button as HTMLButtonElement).click();
  });
  await expect(fixture).toHaveAttribute("data-follow-intent", "following");

  const retryButton = page.getByRole("button", {
    name: "回到聊天最新内容并恢复自动跟随",
    exact: true
  });
  await expect(retryButton).toBeVisible({ timeout: 3_500 });
  await page.evaluate(() => {
    (window as unknown as { restoreFixtureScroll?: () => void })
      .restoreFixtureScroll?.();
  });
  await retryButton.click();
  await waitForStableTail(fixture, surface);
  expect(await tailDistance(surface)).toBeLessThanOrEqual(1);
});

test("a boundary keyboard gesture expires before the next anchored mutation", async ({ page }) => {
  const fixture = page.getByTestId("conversation-scroll-fixture");
  const surface = page.getByRole("region", { name: "当前聊天内容", exact: true });
  await surface.hover();
  await page.mouse.wheel(0, -520);
  await expect(fixture).toHaveAttribute("data-follow-intent", "paused");
  await surface.focus();
  await surface.press("Home");
  await expect.poll(() => surface.evaluate((element) => element.scrollTop))
    .toBeLessThanOrEqual(1);
  await page.waitForTimeout(180);

  await surface.press("Home");
  await page.waitForTimeout(180);
  const anchorBefore = await firstVisibleMessage(surface);
  await page.getByRole("button", { name: "在上方增加内容", exact: true }).click();
  await expect(fixture).toHaveAttribute("data-operation", "idle");
  const anchor = page.locator(`[data-message-id="${anchorBefore.id}"]`);
  await expect.poll(async () => (await anchor.boundingBox())?.y ?? Number.NaN)
    .toBeCloseTo(anchorBefore.top, 0);
});
