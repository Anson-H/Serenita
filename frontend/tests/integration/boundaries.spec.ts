import { expect, test } from "@playwright/test";

test("real API, database, UI and Harness agree on settings, reports, favorites and attachments", async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", error => errors.push(error.message));
  await page.goto("/");
  await page.locator('input[name="account"]').fill("integration");
  await page.locator('input[name="password"]').fill("test-password");
  await page.locator("form").getByRole("button", { name: "登录", exact: true }).click();
  await expect(page.locator(".conversation-composer textarea")).toBeVisible();
  const auth = await (await page.request.get("/api/auth/session")).json();
  const headers = { "X-Serenita-Account-ID": auth.account_id };
  const members = await (await page.request.get("/api/members")).json();
  const memberId = members.default_member_id;
  expect(memberId).toBeTruthy();
  const capabilities = await (await page.request.get("/api/conversations/attachment-capabilities")).json();
  expect(capabilities.file_mime_types).toEqual(["application/pdf", "image/jpeg", "image/png"]);
  await expect(page.locator('input[type="file"][aria-label="附加文件"]')).toHaveAttribute("accept", capabilities.file_mime_types.join(","));

  const created = await page.request.post(`/api/members/${memberId}/reports`, { headers, data: {
    report_type: "其它医疗报告", report_name: "联调报告", report_time: "2026-09-06T09:00:00+08:00", institution_name: "联调机构", other_report: { report_body: "联调报告事实" }
  } });
  expect(created.status(), await created.text()).toBe(201);
  const report = await created.json();
  await page.goto(`/reports/${memberId}/${report.report_id}`);
  await expect(page.getByText("联调报告事实", { exact: true })).toBeVisible();
  const updated = await page.request.patch(`/api/members/${memberId}/reports/${report.report_id}/fields`, { headers, data: { field: "report_name", value: "联调报告已更新" } });
  expect(updated.ok()).toBeTruthy();
  const favorite = await page.request.post("/api/favorites", { headers, data: { member_id: memberId, source_type: "report", source_id: report.report_id, tags: ["联调"] } });
  expect(favorite.ok(), await favorite.text()).toBeTruthy();
  const favoriteId = (await favorite.json()).favorite_id;
  expect((await (await page.request.get(`/api/favorites/${favoriteId}`)).json()).content_snapshot).toContain("联调报告事实");
  await page.goto("/favorites");
  await expect(page.getByText("其它医疗报告 - 联调报告已更新", { exact: true })).toBeVisible();

  await page.goto("/");
  const composer = page.locator(".conversation-composer textarea");
  await composer.fill("联调消息");
  await page.getByRole("button", { name: "发送", exact: true }).click();
  await expect(page.getByText("联调回答：已收到消息。", { exact: true })).toBeVisible();
  const sessionId = decodeURIComponent(new URL(page.url()).pathname.split("/").pop()!);
  await expect.poll(async () => {
    const detail = await (await page.request.get(`/api/conversations/${sessionId}`)).json();
    return detail.pending_turns.length === 0 && detail.records.some(
      (record: { kind: string; content?: string; status?: string }) => record.kind === "assistant"
        && record.status === "completed" && record.content === "联调回答：已收到消息。"
    );
  }).toBeTruthy();
  await page.reload();
  await expect(page.getByText("联调回答：已收到消息。", { exact: true })).toBeVisible();

  const png = Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jB1kAAAAASUVORK5CYII=", "base64");
  await page.locator('input[type="file"][aria-label="附加文件"]').setInputFiles({ name: "联调.png", mimeType: "image/png", buffer: png });
  await expect(page.getByRole("link", { name: "打开附件：联调.png" })).toBeVisible();
  const rejected = await page.request.post("/api/conversations/context-resources", { headers, multipart: { member_id: memberId, model_id: "integration:chat", file: { name: "报告.heic", mimeType: "image/heic", buffer: Buffer.from("heic") } } });
  expect(rejected.status()).toBe(422);
  expect((await rejected.json()).detail.code).toBe("MODEL_FILE_UNSUPPORTED");

  expect((await page.request.post("/api/model-providers/integration/test", { headers, data: {} })).ok()).toBeTruthy();
  const probe = await page.request.post("/api/models/capability-probe/integration%3Achat", { headers });
  expect(probe.ok(), await probe.text()).toBeTruthy();
  const defaults = await (await page.request.get("/api/model-access-settings")).json();
  expect(defaults.defaults.chat.model_id).toBe("integration:chat");
  expect((await page.request.put("/api/account-settings/web-access/providers/exa/credential", { headers, data: { api_key: "integration-web-key" } })).ok()).toBeTruthy();
  expect((await page.request.post("/api/account-settings/web-access/providers/exa/test", { headers, data: {} })).ok()).toBeTruthy();
  expect((await page.request.delete(`/api/members/${memberId}/reports/${report.report_id}`, { headers })).ok()).toBeTruthy();
  const snapshot = await (await page.request.get(`/api/favorites/${favoriteId}`)).json();
  expect(snapshot.source_available).toBe(false);
  expect(snapshot.content_snapshot).toContain("联调报告事实");
  expect((await page.request.delete(`/api/favorites/${favoriteId}`, { headers })).ok()).toBeTruthy();
  expect(errors).toEqual([]);
});


test("report entry exports cover the live API structured fields", async ({ page }) => {
  await page.goto("/");
  const schemas = (await (await page.request.get("http://127.0.0.1:8186/openapi.json")).json()).components.schemas;
  const fields = await page.evaluate(async () => {
    const { ENTRY_FIELDS, REPORT_DETAIL_KEYS } = await import("../../src/features/reports/reportFields");
    return { entries: Object.fromEntries(Object.entries(ENTRY_FIELDS).map(([type, fields]) => [type, fields.map(field => field.key)])), details: REPORT_DETAIL_KEYS };
  });
  for (const [type, keys] of Object.entries(fields.entries)) {
    const detailKey = fields.details[type as keyof typeof fields.details];
    const property = schemas.CreateReportRequest.properties[detailKey];
    const reference = property.anyOf.find((option: { $ref?: string }) => option.$ref).$ref.split("/").pop();
    expect(keys.sort(), type).toEqual(Object.keys(schemas[reference].properties).sort());
  }
  expect(Object.keys(fields.entries).sort()).toEqual(Object.keys(fields.details).sort());
});
