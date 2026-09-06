import { expect, test } from "@playwright/test";

test("one compaction operation exposes both summary layers and retains failure state", async ({ page }) => {
  await page.goto("/tests/fixtures/context-compaction.html");
  const summary = page.locator("summary").filter({ hasText: "上下文压缩" });
  await expect(summary).toHaveCount(1);
  await expect(summary).toContainText("运行中");
  await summary.click();
  const details = summary.locator("..");
  await expect(details).toContainText("历史摘要");
  await expect(details).toContainText("轮次前半段摘要");
  await expect(details).toContainText("turn_prefix");
  await page.getByRole("button", { name: "模拟提交" }).click();
  await expect(summary).toContainText("已完成");
  await expect(summary).toContainText("80,000 → 52,000");
  await page.getByRole("button", { name: "模拟失败" }).click();
  await expect(summary).toContainText("压缩失败");
  await expect(details).toContainText("摘要为空");
  await expect(summary).toHaveCount(1);
});
