import { expect, test, type Locator } from "@playwright/test";
import { mockWorkspace } from "../helpers/workspace";

async function expectCreationLayout(dialog: Locator, width: number, height: number, complete = true) {
  await expect(dialog).toBeVisible();
  const box = (await dialog.boundingBox())!;
  expect(box.width).toBeCloseTo(Math.min(760, width - 30), 0);
  expect(box.height).toBeCloseTo(Math.min(780, height - 30), 0);
  expect(Math.abs(box.x - (width - box.width) / 2)).toBeLessThan(1);
  expect(Math.abs(box.y - (height - box.height) / 2)).toBeLessThan(1);
  await expect(dialog.getByRole("button", { name: "取消", exact: true })).toHaveCount(0);
  await expect(dialog.getByRole("button", { name: "返回", exact: true })).toHaveCount(0);
  if (complete) {
    const button = dialog.getByRole("button", { name: "完成", exact: true });
    await expect(button).toBeInViewport();
    const footer = button.locator("xpath=ancestor::footer");
    const footerBox = (await footer.boundingBox())!;
    expect(Math.abs(footerBox.y + footerBox.height - box.y - box.height)).toBeLessThan(2);
    await expect(footer).toHaveCSS("position", "static");
  }
}

for (const [width, height] of [[1280, 900], [390, 844], [390, 420]]) {
  test(`creation windows share size, footer and header navigation at ${width}x${height}`, async ({ page }, testInfo) => {
    await page.setViewportSize({ width, height });
    await mockWorkspace(page);
    await page.route("**/api/account-settings/lab-dictionary", route => route.fulfill({ json: {
      dictionary_revision: "1", summary: { item_count: 0, category_count: 1, relation_count: 0 }, items: [], categories: [{ category_name: "血常规", item_count: 0, primary_item_count: 0, related_item_count: 0, result_count: 0, report_count: 0 }], relations: [],
    } }));
    await page.route("**/api/members/self/medications**", route => route.fulfill({ json: { items: [], next_cursor: null } }));
    await page.goto("/setting");
    await page.getByRole("button", { name: "检验指标目录", exact: true }).click();
    await page.getByRole("button", { name: "添加指标", exact: true }).click();
    let dialog = page.getByRole("dialog", { name: "添加指标", exact: true });
    await expectCreationLayout(dialog, width, height);
    await dialog.screenshot({ path: testInfo.outputPath("new-indicator.png") });
    await dialog.getByRole("button", { name: "关闭创建窗口", exact: true }).click();

    await page.goto("/reports");
    await page.getByRole("button", { name: "创建医疗报告", exact: true }).click();
    dialog = page.locator(".report-create-dialog");
    await expectCreationLayout(dialog, width, height, false);
    await dialog.getByRole("button", { name: /文字录入/ }).click();
    await expectCreationLayout(dialog, width, height, false);
    await dialog.getByRole("button", { name: /^病理报告/ }).click();
    await expectCreationLayout(dialog, width, height);
    const back = dialog.locator(".dialog-titlebar").getByRole("button", { name: "返回上一级", exact: true });
    const close = dialog.getByRole("button", { name: "关闭创建医疗报告", exact: true });
    const backBox = (await back.boundingBox())!;
    const closeBox = (await close.boundingBox())!;
    expect(backBox.y).toBe(closeBox.y);
    expect(backBox.width).toBe(closeBox.width);
    expect(backBox.x).toBeLessThan(closeBox.x);
    await dialog.locator(".report-create-form-scroll").evaluate(node => { node.scrollTop = node.scrollHeight; });
    await expectCreationLayout(dialog, width, height);
    await back.click();
    await expect(dialog.getByRole("heading", { name: "文字录入", exact: true })).toBeVisible();
    await back.click();
    await expect(back).toHaveCount(0);
    await close.click();

    await page.route("**/api/medication-catalog**", route => route.fulfill({ json: { items: [], total: 0, next_cursor: null } }));
    await page.goto("/setting");
    await page.getByRole("complementary", { name: "设置导航" }).getByRole("button", { name: "药品目录", exact: true }).click();
    await page.getByRole("button", { name: "添加药品", exact: true }).click();
    dialog = page.getByRole("dialog", { name: "添加药品", exact: true });
    await expectCreationLayout(dialog, width, height);
    await dialog.getByLabel("通用名", { exact: true }).fill("目录药品草稿");
    await expect(dialog.getByLabel("通用名", { exact: true })).toHaveValue("目录药品草稿");
    await expectCreationLayout(dialog, width, height);
    await dialog.getByRole("button", { name: "关闭添加药品", exact: true }).click();
    await expect(dialog).toHaveCount(0);
  });
}
