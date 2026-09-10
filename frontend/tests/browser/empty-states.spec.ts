import { expect, test, type Locator } from "@playwright/test";
import { mockWorkspace } from "../helpers/workspace";

async function expectCentered(state: Locator, area: Locator, startAfter?: Locator) {
  await expect(state).toBeVisible();
  const preceding = startAfter ? await startAfter.boundingBox() : null;
  const content = await area.evaluate((node, precedingBottom) => {
    const rect = node.getBoundingClientRect();
    const style = getComputedStyle(node);
    const left = parseFloat(style.paddingLeft);
    const right = parseFloat(style.paddingRight);
    const top = precedingBottom === null ? parseFloat(style.paddingTop) : precedingBottom - rect.y - node.clientTop;
    const bottom = parseFloat(style.paddingBottom);
    return {
      x: rect.x + node.clientLeft + left + (node.clientWidth - left - right) / 2,
      y: rect.y + node.clientTop + top + (node.clientHeight - top - bottom) / 2,
    };
  }, preceding ? preceding.y + preceding.height : null);
  const copy = await state.evaluate(node => {
    const boxes = Array.from(node.children).map(child => child.getBoundingClientRect());
    return {
      x: (Math.min(...boxes.map(b => b.left)) + Math.max(...boxes.map(b => b.right))) / 2,
      y: (Math.min(...boxes.map(b => b.top)) + Math.max(...boxes.map(b => b.bottom))) / 2,
    };
  });
  expect(Math.abs(copy.x - content.x)).toBeLessThan(2);
  expect(Math.abs(copy.y - content.y)).toBeLessThan(2);
  await expect(state.locator(".empty-state-title")).toHaveCSS("font-size", "15px");
  await expect(state.locator(".empty-state-title")).toHaveCSS("font-weight", "700");
}

for (const width of [1280, 800, 390]) {
  for (const colorScheme of ["light", "dark"] as const) {
    test(`empty panes center within usable space at ${width}px in ${colorScheme}`, async ({ page }) => {
      await page.setViewportSize({ width, height: 900 });
      await page.emulateMedia({ colorScheme });
      await mockWorkspace(page);
      await page.route("**/api/members/self/medications**", route => route.fulfill({ json: { items: [], next_cursor: null } }));
      await page.route("**/api/members/self/medication-plans**", route => route.fulfill({ json: { items: [], next_cursor: null } }));
      await page.route("**/api/members/self/medical-logs**", route => route.fulfill({ json: { member_id: "self", medical_logs: [], total: 0, next_cursor: null } }));

      for (const route of ["/health/self/medications/plans", "/health/self/medications/catalog", "/health/self/medical-logs", "/reports", "/favorites"]) {
        await page.goto(route);
        const list = page.locator(route === "/favorites" ? ".favorite-list" : ".report-library-scroll");
        const state = list.locator(".workspace-empty-state");
        await expect(state).not.toContainText("正在读取");
        await expectCentered(state, list);
        await expect(page.locator(".object-list-count")).toHaveCount(0);
        const favorite = route === "/favorites";
        await expect(page.locator(favorite ? ".favorite-detail-column" : ".report-detail-column")).toBeHidden();
        const layout = (await page.locator(favorite ? ".favorite-browser-layout" : ".report-browser-layout").boundingBox())!;
        const column = (await page.locator(favorite ? ".favorite-library-column" : ".report-library-column").boundingBox())!;
        const content = (await page.locator(favorite ? ".favorite-list-panel" : ".health-member-overview").boundingBox())!;
        expect(column.width).toBeCloseTo(layout.width, 0);
        expect(content.width).toBeCloseTo(Math.min(780, layout.width), 0);
        expect(content.x + content.width / 2).toBeCloseTo(layout.x + layout.width / 2, 0);
        if (route.endsWith("/plans") && width === 1280 && colorScheme === "dark") await page.screenshot({ path: "test-results/medication-empty-desktop.png" });
        if (width > 1000) await expectCentered(page.locator(".conversation-list-empty"), page.locator(".conversation-list"));
        expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
      }
      await page.screenshot({ path: `test-results/empty-states-${width}-${colorScheme}.png` });
    });
  }
}

test("medication search and read-only empty lists keep their usable height", async ({ page }) => {
  await mockWorkspace(page);
  await page.route("**/api/members", route => route.fulfill({ json: { access_revision: 1, default_member_id: "self", initial_member_id: "self", last_member_id: "self", startup_mode: "last_used", members: [{ member_id: "self", member_name: "本人", is_owned: false, can_edit: false, permission: "read", account_id: "owner", owner_account: "owner" }] } }));
  await page.route("**/api/members/self/medications**", route => route.fulfill({ json: { items: [], next_cursor: null } }));
  await page.route("**/api/members/self/medications**", route => route.fulfill({ json: { items: new URL(route.request().url()).searchParams.get("query") ? [] : [{ medication_id: "drug1", generic_name: "示例药品", strength: "5 mg", sources: [], batches: [] }], next_cursor: null } }));
  await page.goto("/health/self/medications/catalog");
  await expect(page.locator(".report-timeline-item")).toHaveCount(1);
  await page.getByRole("searchbox", { name: "搜索用药资料" }).fill("不存在的药品");
  const list = page.locator(".report-library-scroll");
  await expect(list).toContainText("没有匹配的药品");
  await expect(page.getByRole("button", { name: "添加药品", exact: true })).toHaveCount(0);
  await expect(list).toHaveCSS("padding-bottom", "15px");
  await expectCentered(list.locator(".workspace-empty-state"), list);
});


test("settings catalog empty states fill the area below the create entry", async ({ page }) => {
  await mockWorkspace(page);
  await page.route("**/api/account-settings/lab-dictionary", route => route.fulfill({ json: {
    dictionary_revision: "1", summary: { item_count: 0, category_count: 0, relation_count: 0 }, items: [], categories: [], relations: [],
  } }));
  for (const title of ["检验分类目录", "检验指标目录"]) {
    await page.goto("/setting");
    await page.getByRole("button", { name: title, exact: true }).click();
    const area = page.locator(".dictionary-entity-list");
    await expectCentered(area.locator(".workspace-empty-state"), area, area.locator(".dictionary-grouped-list"));
    await expect(page.locator(".object-list-count")).toHaveCount(0);
  }
});

async function expectCountFollowsList(count: Locator) {
  await expect(count).toBeVisible();
  await count.scrollIntoViewIfNeeded();
  const geometry = await count.evaluate(node => {
    const rect = node.getBoundingClientRect();
    const list = node.previousElementSibling!.getBoundingClientRect();
    return { gap: rect.top - list.bottom, center: rect.left + rect.width / 2 - list.left - list.width / 2 };
  });
  expect(Math.abs(geometry.gap - 15)).toBeLessThan(1);
  expect(Math.abs(geometry.center)).toBeLessThan(1);
}

for (const width of [1280, 390]) for (const length of [1, 40]) {
  test(`catalog counts follow ${length} rows by 15px at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    await mockWorkspace(page);
    await page.route("**/api/account-settings/lab-dictionary", route => route.fulfill({ json: {
      dictionary_revision: "1", summary: { item_count: length, category_count: length, relation_count: length },
      items: Array.from({ length }, (_, i) => ({ item_id: `i${i}`, item_name_zh: `指标${i}`, aliases: [], primary_category_name: `分类${i}`, related_category_names: [], usage_by_category: [], result_count: 0, report_count: 0 })),
      categories: Array.from({ length }, (_, i) => ({ category_name: `分类${i}`, item_count: 1, primary_item_count: 1, related_item_count: 0, result_count: 0, report_count: 0 })),
      relations: [],
    } }));
    for (const title of ["检验分类目录", "检验指标目录"]) {
      await page.goto("/setting");
      await page.getByRole("button", { name: title, exact: true }).click();
      const count = page.locator(".dictionary-entity-list > .object-list-count");
      await expect(count).toContainText(`共 ${length} 条`);
      await expectCountFollowsList(count);
    }
  });

  test(`remote model count scrolls with ${length} rows at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    await mockWorkspace(page);
    await page.route("**/api/model-providers", route => route.fulfill({ json: { providers: [{ provider_id: "test", provider_name: "测试提供方", api_url: "https://test.invalid", official_url: "", has_api_key: true }] } }));
    await page.route("**/api/model-providers/test/models", route => route.fulfill({ json: { models: Array.from({ length }, (_, i) => ({ remote_model_id: `model${i}` })) } }));
    await page.goto("/setting");
    await page.getByRole("button", { name: "模型提供方", exact: true }).click();
    await page.getByRole("button", { name: "测试提供方", exact: true }).click();
    await page.getByRole("button", { name: "添加模型", exact: true }).click();
    const count = page.locator(".model-picker-list > .object-list-count");
    await expect(count).toHaveText(`共 ${length} 个模型`);
    await expectCountFollowsList(count);
    const group = page.locator(".model-picker-group").first();
    await group.locator(".root-disclosure-toggle").click();
    await expectCountFollowsList(count);
  });
}
