import { expect, test } from "@playwright/test";

for (const width of [1280, 390]) {
  test(`medical logs create, autosave, failure retention and deletion at ${width}px`, async ({ page }) => {
    test.setTimeout(90000);
    await page.setViewportSize({ width, height: 900 });
    await page.goto("/");
    await page.locator('input[name="account"]').fill("integration");
    await page.locator('input[name="password"]').fill("test-password");
    await page.locator("form").getByRole("button", { name: "登录", exact: true }).click();
    await expect(page.locator(".conversation-composer textarea")).toBeVisible();
    const auth = await (await page.request.get("/api/auth/session")).json();
    const headers = { "X-Serenita-Account-ID": auth.account_id };
    const created = await page.request.post("/api/members", { headers, data: { member_name: `日记验收${width}` } });
    const memberId = (await created.json()).member_id;
    const base = `/api/members/${memberId}/medical-logs`;
    await page.goto(`/health/${memberId}`);
    await page.getByRole("button", { name: "健康日记", exact: true }).click();
    await expect(page).toHaveURL(new RegExp(`/health/${memberId}/medical-logs$`));
    await page.getByRole("button", { name: "创建健康日记", exact: true }).click();
    await page.getByLabel("日记标题", { exact: true }).fill("发热经过");
    await page.getByLabel("日记内容", { exact: true }).fill("家属描述：可能昨天发热，具体日期未明确。");
    await page.getByRole("button", { name: "完成", exact: true }).click();
    await expect(page).toHaveURL(new RegExp(`/medical-logs/[^/]+$`));
    const logId = page.url().split("/").pop()!;
    const read = async () => (await (await page.request.get(`${base}/${logId}`)).json()).medical_log;
    const today = await page.evaluate(() => {
      const now = new Date();
      return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(now.getDate()).padStart(2, "0")}`;
    });
    expect((await read()).recorded_on).toBe(today);
    expect(Object.keys(await read()).sort()).toEqual(["medical_log_id", "member_id", "recorded_on", "title", "content", "created_at", "updated_at"].sort());
    await expect(page.getByRole("heading", { name: "关联医疗报告", exact: true })).toHaveCount(0);
    await page.getByLabel("日记内容", { exact: true }).fill("家属描述：可能昨日发热，今天好转。");
    await expect.poll(async () => (await read()).content).toBe("家属描述：可能昨日发热，今天好转。");
    let fail = true;
    await page.route(`**${base}/${logId}`, async route => {
      if (route.request().method() === "PATCH" && fail) return route.fulfill({ status: 503, json: { detail: { message: "验收模拟保存失败" } } });
      return route.continue();
    });
    await page.getByLabel("日记标题", { exact: true }).fill("失败时保留的草稿");
    await expect(page.getByRole("button", { name: "重试保存", exact: true })).toBeVisible();
    if (width === 390) await page.getByRole("button", { name: "关闭通知", exact: true }).click();
    if (width === 390) await page.locator(".medical-log-detail").getByRole("button", { name: "返回上一级", exact: true }).click();
    else await page.getByRole("button", { name: "医疗报告", exact: true }).click();
    await expect(page).toHaveURL(new RegExp(`/medical-logs/${logId}$`));
    await expect(page.getByLabel("日记标题", { exact: true })).toHaveValue("失败时保留的草稿");
    expect((await read()).title).toBe("发热经过");
    fail = false;
    await page.getByRole("button", { name: "重试保存", exact: true }).click();
    await expect.poll(async () => (await read()).title).toBe("失败时保留的草稿");
    await page.reload();
    await expect(page.getByLabel("日记标题", { exact: true })).toHaveValue("失败时保留的草稿");
    await page.getByRole("button", { name: "删除日记", exact: true }).click();
    await expect(page).toHaveURL(new RegExp(`/medical-logs$`));
    expect((await page.request.get(`${base}/${logId}`)).status()).toBe(404);
    await page.request.delete(`/api/members/${memberId}`, { headers });
  });
}
