import { expect, test } from "@playwright/test";

for (const width of [1280, 375]) {
  test(`compression updates one visible operation and expands chunk records at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    await page.goto("/tests/fixtures/context-compaction.html");
    const activity = page.locator(".context-record");
    await expect(activity).toHaveCount(1);
    await expect(activity.getByRole("status")).toHaveText("运行中");
    await expect(activity.getByRole("status")).toBeVisible();
    await expect(activity.locator("summary")).toContainText("80,000 → —，目标 60,000");
    await expect(page.getByText("摘要分块1", { exact: true })).toHaveCount(0);
    await activity.locator("summary").click();
    await expect(activity.locator(".operation-record-body")).toContainText("摘要分块1");
    await expect(activity.locator(".operation-record-body")).toContainText("摘要分块2");
    await expect(activity.locator(".operation-record-body")).toContainText("prompt_tokens");
    await page.getByRole("button", { name: "模拟提交" }).click();
    await expect(activity).toHaveCount(1);
    await expect(activity.getByRole("status")).toHaveText("已完成");
    await expect(activity.locator("summary")).toContainText("80,000 → 52,000，目标 60,000");
    await expect(activity.locator(".operation-record-body")).toContainText("80,000 → 52,000，目标 60,000");
    await page.getByRole("button", { name: "模拟失败" }).click();
    await expect(activity.getByRole("status")).toHaveText("压缩失败");
    await expect(activity.locator("summary")).toContainText("80,000 → —，目标 60,000");
    await expect(activity.locator(".operation-record-error")).toContainText("摘要为空");
    await expect(activity.getByRole("status")).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  });
}


test("related reports retain their rows and disable deleted or unauthorized sources", async ({ page }) => {
  await page.goto("/tests/fixtures/related-content.html");
  await page.locator("summary").click();
  await expect(page.getByRole("button", { name: "查阅：deleted，医疗报告已删除", exact: true })).toBeDisabled();
  await expect(page.getByRole("button", { name: "查阅：forbidden，无权访问", exact: true })).toBeDisabled();
  await expect(page.getByRole("button", { name: "查阅：available", exact: true })).toBeEnabled();
  await expect(page.locator("body")).not.toHaveAttribute("data-opened");
  await page.getByRole("button", { name: "查阅：available", exact: true }).click();
  await expect(page.locator("body")).toHaveAttribute("data-opened", "true");
});

for (const width of [1280, 390]) {
  test(`health changes share one related content section and preserve availability at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    await page.goto("/tests/fixtures/related-content.html?mixed");
    await expect(page.locator("summary")).toHaveCount(1);
    await expect(page.locator("summary")).toContainText("相关内容");
    await expect(page.locator("summary")).toContainText("9 项");
    await page.locator("summary").click();
    await expect(page.getByRole("link", { name: "更新：今天的随记，已更新", exact: true })).toHaveAttribute("href", "/health/available/medical-logs/diary");
    await expect(page.getByRole("link", { name: "更新：早间用药安排", exact: true })).toHaveAttribute("href", "/health/available/medications/plans/plan");
    await expect(page.getByRole("link", { name: "更新：现有药品库存", exact: true })).toHaveAttribute("href", "/health/available/medications/catalog/drug/batches/batch");
    await expect(page.getByRole("link", { name: "更新：体重", exact: true })).toHaveAttribute("href", "/health/available/body-metrics/body?record=weight");
    await expect(page.getByRole("button", { name: "更新：共享日记，无权访问", exact: true })).toBeDisabled();
    await expect(page.getByRole("button", { name: "删除：删除的日记，已删除", exact: true })).toBeDisabled();
    await page.reload();
    await page.locator("summary").click();
    await expect(page.locator(".related-report-item")).toHaveCount(9);
    await expect(page.getByRole("link", { name: "更新：今天的随记，已更新", exact: true })).toBeVisible();
  });
}
