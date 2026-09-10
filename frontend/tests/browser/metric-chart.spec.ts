import { expect, test } from "@playwright/test";

test("a hundred chart points use one tab stop and arrows open the chosen bucket", async ({
  page,
}) => {
  await page.goto("/tests/fixtures/metric-chart.html");
  await page.getByRole("button", { name: "图表之前" }).focus();
  await page.keyboard.press("Tab");
  const points = page.locator(".bm-point");
  await expect(points).toHaveCount(100);
  await expect(points.nth(0)).toBeFocused();
  await page.keyboard.press("ArrowRight");
  await expect(points.nth(1)).toBeFocused();
  await page.keyboard.press("End");
  await expect(points.nth(99)).toBeFocused();
  await page.keyboard.press("Space");
  await expect(page.getByLabel("已选日期")).toHaveText("2026-04-10");
  await page.keyboard.press("Home");
  await page.keyboard.press("Enter");
  await expect(page.getByLabel("已选日期")).toHaveText("2026-01-01");
  await page.keyboard.press("Tab");
  await expect(page.getByRole("button", { name: "图表之后" })).toBeFocused();
  await expect(page.locator('.bm-point[tabindex="0"]')).toHaveCount(1);
});
