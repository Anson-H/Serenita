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
  for (const type of ["检验报告", "检查报告", "病理报告", "手术报告", "门诊病历", "急诊病历", "其它医疗报告"]) {
    await page.goto(`/health/${memberId}`);
    await expect(page.getByRole("button", { name: "创建医疗报告", exact: true })).toBeVisible();
    await page.getByRole("button", { name: "创建医疗报告", exact: true }).click();
    await page.getByRole("button", { name: /文字录入/ }).click();
    await page.getByRole("dialog").getByRole("button", { name: new RegExp(`^${type}`) }).click();
    const dialog = page.getByRole("dialog");
    if (type === "检验报告") {
      await dialog.getByRole("button", { name: "医疗报告名称", exact: true }).click();
      await page.getByRole("option", { name: "页面验收分类", exact: true }).click();
      await dialog.getByLabel("页面验收指标结果", { exact: true }).fill("5.6");
      await dialog.getByLabel("页面验收指标参考值", { exact: true }).fill("3–6");
    } else {
      await dialog.locator('input[name="report_name"]').fill(`页面${type}`);
      if (type === "检查报告") await dialog.locator('[name="exam_name"]').fill("页面检查项目");
      if (type === "病理报告") await dialog.locator('[name="diagnosis"]').fill("页面病理记录");
      if (type === "手术报告") await dialog.locator('[name="procedure_description"]').fill("页面手术经过");
      if (type === "门诊病历" || type === "急诊病历") {
        await dialog.locator('[name="chief_complaint"]').fill("腹痛，原因待查");
        await dialog.locator('[name="diagnosis"]').fill("待查");
      }
      if (type === "急诊病历") {
        await dialog.locator('[name="discharge_diagnosis"]').fill("出院诊断待查");
        await dialog.locator('[name="discharge_instructions"]').fill("按原件记录复诊");
      }
      if (type === "其它医疗报告") await dialog.locator('[name="report_body"]').fill("页面报告正文");
    }
    await dialog.locator('[name="institution_name"]').fill("页面机构");
    const createdResponse = page.waitForResponse(response => response.url().endsWith(`/members/${memberId}/reports`) && response.request().method() === "POST");
    await dialog.getByRole("button", { name: "完成", exact: true }).click();
    const response = await createdResponse;
    expect(response.status(), await response.text()).toBe(201);
    expect(response.request().headers()["x-serenita-account-id"]).toBe(auth.account_id);
    const report = await response.json();
    await expect(dialog).toBeHidden();
    if (type === "门诊病历" || type === "急诊病历") {
      await expect(page.locator(".report-detail-pane")).toContainText("腹痛，原因待查");
      await page.getByRole("button", { name: "编辑主诉", exact: true }).click();
      const complaint = page.getByRole("textbox", { name: "主诉", exact: true });
      await complaint.fill("主诉已修正");
      const updated = page.waitForResponse(response => response.url().endsWith(`/reports/${report.report_id}/fields`) && response.request().method() === "PATCH");
      await complaint.press("Tab");
      expect((await updated).ok()).toBeTruthy();
      if (type === "急诊病历") {
        await expect(page.locator(".report-detail-pane")).toContainText("出院诊断待查");
        await expect(page.locator(".report-detail-pane")).toContainText("按原件记录复诊");
      }
    }
    await expect(page.locator(".report-detail-pane")).toContainText("页面机构");
    await page.getByRole("button", { name: "编辑就诊机构", exact: true }).click();
    const field = page.getByRole("textbox", { name: "就诊机构", exact: true });
    await field.fill("页面机构已更新");
    const saved = page.waitForResponse(response => response.url().endsWith(`/reports/${report.report_id}/fields`) && response.request().method() === "PATCH");
    await field.press("Tab");
    expect((await saved).ok()).toBeTruthy();
    await expect(page.getByRole("button", { name: "编辑就诊机构", exact: true })).toContainText("页面机构已更新");
    const deleted = page.waitForResponse(response => response.url().endsWith(`/reports/${report.report_id}`) && response.request().method() === "DELETE");
    await page.getByRole("button", { name: "删除医疗报告", exact: true }).click();
    expect((await deleted).ok()).toBeTruthy();
    await expect(page.getByRole("button", { name: "删除医疗报告", exact: true })).toBeHidden();
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
  await expect(page.getByRole("button", { name: "创建医疗报告", exact: true })).toBeVisible();
});


test("eight history fields share API state and clear independently", async ({ page }) => {
  await page.goto("/");
  await page.locator('input[name="account"]').fill("integration");
  await page.locator('input[name="password"]').fill("test-password");
  await page.locator("form").getByRole("button", { name: "登录", exact: true }).click();
  await expect(page.locator(".conversation-composer textarea")).toBeVisible();
  const memberId = (await (await page.request.get("/api/members")).json()).default_member_id;
  await page.goto(`/health/${memberId}`);
  await page.getByRole("button", { name: "查看联调成员的个人信息", exact: true }).click();
  const history = page.getByRole("region", { name: "既往史", exact: true });
  await expect(history.getByRole("textbox")).toHaveCount(8);
  await history.getByRole("textbox", { name: "既往疾病史", exact: true }).fill("平素体健；否认高血压病史");
  await history.getByRole("textbox", { name: "过敏史", exact: true }).fill("无");
  await history.getByRole("textbox", { name: "输血接种史", exact: true }).fill("不详");
  await expect.poll(async () => (await (await page.request.get(`/api/members/${memberId}/medical-history`)).json()).history.transfusion_vaccination_history.text).toBe("不详");
  await page.reload();
  await page.getByRole("button", { name: "查看联调成员的个人信息", exact: true }).click();
  await expect(history.getByRole("textbox", { name: "过敏史", exact: true })).toHaveValue("无");
  await history.getByRole("textbox", { name: "过敏史", exact: true }).fill("");
  await expect.poll(async () => (await (await page.request.get(`/api/members/${memberId}/medical-history`)).json()).history.allergy_history.text).toBeNull();
  const saved = await (await page.request.get(`/api/members/${memberId}/medical-history`)).json();
  expect(saved.history.past_medical_history.text).toBe("平素体健；否认高血压病史");
  expect(saved.history.transfusion_vaccination_history.text).toBe("不详");
  expect(saved.history.allergy_history.updated_at).toBeTruthy();
});

test("visit report analysis actions enter the Harness with the selected member and report", async ({ page }) => {
  await page.goto("/");
  await page.locator('input[name="account"]').fill("integration");
  await page.locator('input[name="password"]').fill("test-password");
  await page.locator("form").getByRole("button", { name: "登录", exact: true }).click();
  await expect(page.locator(".conversation-composer textarea")).toBeVisible();
  const auth = await (await page.request.get("/api/auth/session")).json();
  const headers = { "X-Serenita-Account-ID": auth.account_id };
  const memberId = (await (await page.request.get("/api/members")).json()).default_member_id;
  for (const [type, key] of [["门诊病历", "outpatient_report"], ["急诊病历", "emergency_report"]]) {
    const created = await page.request.post(`/api/members/${memberId}/reports`, { headers, data: {
      report_type: type, report_name: `解读入口${type}`, report_time: "2026-09-01T09:00:00+08:00", [key]: { chief_complaint: "合成验收主诉" }
    } });
    expect(created.ok(), await created.text()).toBeTruthy();
    const reportId = (await created.json()).report_id;
    for (const action of ["开始解读", "重新解读"]) {
      if (action === "重新解读") {
        const saved = await page.request.patch(`/api/members/${memberId}/reports/${reportId}/fields`, { headers, data: { field: "analysis_content", value: "已有解读结果，测试页面重新解读入口。" } });
        expect(saved.ok(), await saved.text()).toBeTruthy();
      }
      await page.goto(`/reports/${memberId}/${reportId}`);
      const submitted = page.waitForResponse(response => response.url().endsWith("/api/conversations/messages") && response.request().method() === "POST");
      await page.getByRole("button", { name: action, exact: true }).click();
      const response = await submitted;
      expect(response.ok(), await response.text()).toBeTruthy();
      const payload = response.request().postDataJSON();
      expect(payload.member_id).toBe(memberId);
      expect(payload.context_resources).toEqual(expect.arrayContaining([expect.objectContaining({ resource_type: "report", resource_id: reportId, member_id: memberId })]));
      await expect(page).toHaveURL(/\/chat\//);
      await expect(page.getByText("联调回答：已收到消息。", { exact: true })).toBeVisible();
    }
    expect((await page.request.delete(`/api/members/${memberId}/reports/${reportId}`, { headers })).ok()).toBeTruthy();
  }
});
