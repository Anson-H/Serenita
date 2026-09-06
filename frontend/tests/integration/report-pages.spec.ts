import { expect, test } from "@playwright/test";

test("all report forms create, edit and delete through the page and ordinary APIs", async ({ page }) => {
  test.setTimeout(90000);
  const errors: string[] = [];
  page.on("pageerror", error => errors.push(error.message));
  await page.goto("/");
  await page.locator('input[name="account"]').fill("integration");
  await page.locator('input[name="password"]').fill("test-password");
  await page.locator("form").getByRole("button", { name: "登录", exact: true }).click();
  await expect(page.locator(".conversation-composer textarea")).toBeVisible();
  const auth = await (await page.request.get("/api/auth/session")).json();
  const headers = { "X-Serenita-Account-ID": auth.account_id };
  const memberId = (await (await page.request.get("/api/members")).json()).default_member_id;
  const dictionaryPath = "/api/account-settings/lab-dictionary";
  const dictionary = await (await page.request.get(dictionaryPath)).json();
  const category = await page.request.post(`${dictionaryPath}/categories`, { headers, data: {
    category_name: "页面验收分类", description: null, expected_dictionary_revision: dictionary.dictionary_revision
  } });
  expect(category.ok(), await category.text()).toBeTruthy();
  const item = await page.request.post(`${dictionaryPath}/items`, { headers, data: {
    item_name_zh: "页面验收指标", aliases: [], description: null, primary_category_name: "页面验收分类", related_category_names: [],
    expected_dictionary_revision: (await category.json()).dictionary.dictionary_revision
  } });
  expect(item.ok(), await item.text()).toBeTruthy();
  const conversationWrites: string[] = [];
  page.on("request", request => {
    if (new URL(request.url()).pathname.startsWith("/api/conversations") && request.method() !== "GET") conversationWrites.push(request.url());
  });
  for (const type of ["检验报告", "检查报告", "病理报告", "手术报告", "其它报告"]) {
    await page.goto(`/health/${memberId}`);
    await expect(page.getByRole("button", { name: "新增报告", exact: true })).toBeVisible();
    await page.getByRole("button", { name: "新增报告", exact: true }).click();
    await page.getByRole("button", { name: /文字录入/ }).click();
    await page.getByRole("dialog").getByRole("button", { name: new RegExp(`^${type}`) }).click();
    const dialog = page.getByRole("dialog");
    if (type === "检验报告") {
      await dialog.getByRole("button", { name: "报告名称", exact: true }).click();
      await page.getByRole("option", { name: "页面验收分类", exact: true }).click();
      await dialog.getByLabel("页面验收指标结果", { exact: true }).fill("5.6");
      await dialog.getByLabel("页面验收指标参考值", { exact: true }).fill("3–6");
    } else {
      await dialog.locator('input[name="report_name"]').fill(`页面${type}`);
      if (type === "检查报告") await dialog.locator('[name="exam_name"]').fill("页面检查项目");
      if (type === "病理报告") await dialog.locator('[name="diagnosis"]').fill("页面病理记录");
      if (type === "手术报告") await dialog.locator('[name="procedure_description"]').fill("页面手术经过");
      if (type === "其它报告") await dialog.locator('[name="report_body"]').fill("页面报告正文");
    }
    await dialog.locator('[name="institution_name"]').fill("页面机构");
    const createdResponse = page.waitForResponse(response => response.url().endsWith(`/members/${memberId}/reports`) && response.request().method() === "POST");
    await dialog.getByRole("button", { name: "保存报告", exact: true }).click();
    const response = await createdResponse;
    expect(response.status(), await response.text()).toBe(201);
    expect(response.request().headers()["x-serenita-account-id"]).toBe(auth.account_id);
    const report = await response.json();
    await expect(dialog).toBeHidden();
    await expect(page.locator(".report-detail-pane")).toContainText("页面机构");
    await page.getByRole("button", { name: "修改就诊机构", exact: true }).click();
    const field = page.getByRole("textbox", { name: "就诊机构", exact: true });
    await field.fill("页面机构已修改");
    const saved = page.waitForResponse(response => response.url().endsWith(`/reports/${report.report_id}/fields`) && response.request().method() === "PATCH");
    await field.press("Tab");
    expect((await saved).ok()).toBeTruthy();
    await expect(page.getByRole("button", { name: "修改就诊机构", exact: true })).toContainText("页面机构已修改");
    const deleted = page.waitForResponse(response => response.url().endsWith(`/reports/${report.report_id}`) && response.request().method() === "DELETE");
    await page.getByRole("button", { name: "删除报告", exact: true }).click();
    expect((await deleted).ok()).toBeTruthy();
    await expect(page.getByRole("button", { name: "删除报告", exact: true })).toBeHidden();
  }
  expect(conversationWrites).toEqual([]);
  expect(errors).toEqual([]);
});


test("sidebar member selection persists before entering the report archive", async ({ page }) => {
  await page.goto("/");
  await page.locator('input[name="account"]').fill("integration");
  await page.locator('input[name="password"]').fill("test-password");
  await page.locator("form").getByRole("button", { name: "登录", exact: true }).click();
  await expect(page.locator(".conversation-composer textarea")).toBeVisible();
  const saved = page.waitForResponse(response => response.url().endsWith("/account-settings/member-preferences") && response.request().method() === "PATCH");
  await page.getByRole("button", { name: "打开健康档案：联调成员 · 默认成员", exact: true }).click();
  const response = await saved;
  expect(response.ok(), await response.text()).toBeTruthy();
  await expect(page.getByRole("button", { name: "新增报告", exact: true })).toBeVisible();
});
