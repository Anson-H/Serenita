import { expect, test, type Page } from "@playwright/test";
import { MEDICAL_HISTORY_FIELDS } from "../../src/api/medicalHistoryTypes";
import type { Member } from "../../src/api/memberApi";

function initialState() {
  const base = { account_id: "actor", owner_account: "actor", sex: null, birth_date: null, blood_type: null, is_owned: true, can_edit: true, permission: "owner" as const };
  return {
    members: [
      { ...base, member_id: "self", member_name: "本人", is_default: true },
      { ...base, member_id: "family", member_name: "妈妈", is_default: false },
      { ...base, member_id: "shared", member_name: "本人", is_default: false, account_id: "owner", owner_account: "owner", is_owned: false, can_edit: false, permission: "read" as const }
    ] as Member[],
    defaultId: "self" as string | null, mode: "last_used", last: "family" as string | null, revision: 1, requests: [] as string[],
    histories: {} as Record<string, Record<string, { text: string | null; updated_at: string | null }>>,
    reportSources: [] as Array<Record<string, unknown>>,
  };
}
type State = ReturnType<typeof initialState>;

async function mockApi(page: Page, state: State) {
  await page.route(url => url.pathname.startsWith("/api/"), async route => {
    const request = route.request();
    const path = new URL(request.url()).pathname.slice(4);
    const method = request.method();
    state.requests.push(`${method} ${path}`);
    const body = request.postData() && request.headers()["content-type"]?.includes("application/json")
      ? request.postDataJSON()
      : {};
    const json = (value: unknown, status = 200) => route.fulfill({ status, json: value });
    if (path === "/conversations/attachment-capabilities") return json({ model_id: new URL(route.request().url()).searchParams.get("model_id"), file_mime_types: ["image/jpeg", "image/png", "application/pdf"] });
    const setDefault = (id: string) => {
      state.defaultId = id;
      for (const member of state.members) member.is_default = member.member_id === id;
      state.revision++;
    };
    const collection = () => {
      if (!state.members.some(member => member.member_id === state.defaultId)) {
        const replacement = state.members.find(member => member.is_owned) ?? state.members[0];
        if (replacement) setDefault(replacement.member_id);
        else state.defaultId = null;
      }
      const last = state.last === null ? null : state.members.some(member => member.member_id === state.last) ? state.last : state.defaultId;
      return { members: state.members, default_member_id: state.defaultId, startup_mode: state.mode,
        last_member_id: last, initial_member_id: state.mode === "default" ? state.defaultId : last, access_revision: state.revision };
    };
    if (path === "/auth/session") return json({ authenticated: true, account_id: "actor", account: "actor", account_name: "测试账号" });
    if (path === "/members/access-events") return route.fulfill({ contentType: "text/event-stream", body: "retry: 60000\n\n" });
    if (path === "/members" && method === "GET") return json(collection());
    if (path === "/members" && method === "POST") {
      const createsFirst = state.members.length === 0;
      const template = state.members[0] ?? { account_id: "actor", owner_account: "actor", sex: null, birth_date: null, blood_type: null, is_owned: true, can_edit: true, permission: "owner" as const };
      const created = { ...template, ...body, member_id: `created-${++state.revision}`, is_default: false };
      state.members.push(created);
      if (createsFirst || body.set_as_default) setDefault(created.member_id);
      return json(created, 201);
    }
    if (path === "/account-settings/member-preferences") {
      if (body.startup_mode) { state.mode = body.startup_mode; state.revision++; }
      if (body.default_member_id) setDefault(body.default_member_id);
      if ("last_member_id" in body) state.last = body.last_member_id;
      return json(collection());
    }
    if (path === "/conversations") return json({ sessions: [], has_more: false, next_cursor: null });
    if (path === "/conversations/history") return json({ session_id: "history", member_id: "shared", member_name: "原共享成员", access_state: state.members.some(member => member.member_id === "shared") ? "available" : "history_only", title: "历史聊天", parent_session_id: null, seed_event_count: 0, fork_available: false, records: [], pending_turns: [], queued_inputs: [], resource_states: [] });
    if (path === "/favorites") return json({ favorites: [], has_more: false, next_cursor: null });
    if (path === "/models") return json({ models: [] });
    if (path === "/model-providers") return json({ providers: [] });
    if (path === "/model-access-settings") return json({ defaults: { chat: null, title: null, vision_parse: null, compact: null } });
    if (path === "/account-settings/conversation-preferences") return json(method === "PUT" ? body : {
      composer_submit_shortcut: "enter",
      base_context_display_modes: { system_prompt: "conversation_start", tool_catalog: "conversation_start", skill_catalog: "conversation_start", runtime_context: "conversation_start" },
      is_context_window_usage_visible: false,
      is_related_content_visible: true,
      is_token_usage_visible: false,
      visible_context_types: [],
      tool_display_types: ["model_tool_request", "tool_call"]
    });
    if (path === "/account-settings/web-access") return json({ is_enabled: false, active_provider_id: "exa", providers: [] });
    const memberId = path.split("/")[2];
    const member = state.members.find(item => item.member_id === memberId);
    if (path.startsWith("/members/") && !member) return json({ detail: { code: "MEMBER_ACCESS_UNAVAILABLE", message: "已撤权" } }, 403);
    if (path === `/members/${memberId}/medical-history`) {
      const history = state.histories[memberId] ??= Object.fromEntries(MEDICAL_HISTORY_FIELDS.map(([field]) => [field, { text: null, updated_at: null }]));
      if (method === "PATCH") {
        if (!member!.can_edit) return json({ detail: { message: "只读成员" } }, 403);
        for (const [field, value] of Object.entries(body)) history[field] = { text: typeof value === "string" ? value.trim() || null : null, updated_at: "2026-09-07T12:00:00+08:00" };
      }
      return json({ member_id: memberId, history });
    }
    if (path === `/members/${memberId}` && method === "PATCH") {
      Object.assign(member!, body); state.revision++;
      if (body.set_as_default) setDefault(memberId);
      return json(member);
    }
    if (path === `/members/${memberId}` && method === "DELETE") {
      if (!member!.is_owned) return json({ detail: { message: "只有所有者可以删除" } }, 403);
      state.members = state.members.filter(item => item.member_id !== memberId); state.revision++;
      return json({ member_id: memberId, deleted: true, pending_file_cleanup: 0, collection: collection() });
    }
    const reportDetail = () => ({ member_id: memberId, report_id: "SAME-ID", report_type: "其它医疗报告", report_name: `${memberId}-报告`, report_time: "2026-08-01T12:00:00+08:00", created_at: "2026-08-01T12:00:00+08:00", updated_at: "2026-08-01T12:00:00+08:00", institution_name: "测试机构", has_analysis: false, analysis_content: "", analysis_outdated: false, flagged_count: 0, total_count: 1, sources: state.reportSources, lab_test_results: [], other_report: { report_body: "测试报告内容" }, examination_report: null, pathology_report: null, surgery_report: null });
    if (path.endsWith("/reports")) return json({ reports: [], total: 0 });
    if (path.endsWith("/reports/SAME-ID/source-files") && method === "POST") {
      state.reportSources = [{ resource_id: "FILE-SUPPLEMENTED", filename: "FILE-SUPPLEMENTED.jpg", mime_type: "image/jpeg", size_bytes: 1024, source_kind: "photo", source_type: "uploaded_file", download_url: `/api/members/${memberId}/reports/SAME-ID/source-files/FILE-SUPPLEMENTED`, created_at: "2026-08-01T12:00:00+08:00", is_primary: true }];
      return json(reportDetail(), 201);
    }
    if (path.endsWith("/reports/SAME-ID")) return json(reportDetail());
    return json({ detail: { message: `未模拟 ${method} ${path}` } }, 404);
  });
}

async function openSidebar(page: Page) {
  const toggle = page.getByRole("button", { name: "展开侧边栏", exact: true });
  if (await toggle.isVisible()) await toggle.click();
}

async function choose(page: Page, label: string) {
  await openSidebar(page);
  await page.getByRole("button", { name: "切换成员", exact: true }).click();
  await page.getByRole("dialog", { name: "切换成员", exact: true })
    .getByRole("button", { name: label, exact: true }).click();
}

async function newChat(page: Page) {
  await expect(page.getByRole("dialog", { name: "切换成员", exact: true })).toHaveCount(0);
  if ((page.viewportSize()?.width ?? 1280) <= 650) {
    await expect(page.getByRole("button", { name: "展开侧边栏", exact: true })).toBeVisible();
  }
  await openSidebar(page);
  await page.getByRole("button", { name: "发起新聊天", exact: true }).click();
}

const width = 390;

test("chat member selection stays in chat and health has no duplicate picker", async ({ page }) => {
  const state = initialState(); await mockApi(page, state);
  await page.setViewportSize({ width, height: 900 }); await page.goto("/");
  const picker = page.getByRole("button", { name: "选择成员", exact: true });
  await expect(picker).toContainText("妈妈");
  await picker.click();
  await page.getByRole("option", { name: "本人 · 默认成员", exact: true }).click();
  await expect(picker).toContainText("本人");
  await expect(page).toHaveURL(/\/$/);
  expect(state.last).toBe("self");
  await picker.click();
  await page.getByRole("option", { name: "不关联成员", exact: true }).click();
  await expect(picker).toContainText("不关联成员");
  expect(state.last).toBeNull();
  await picker.click();
  await page.getByRole("option", { name: "妈妈", exact: true }).click();
  await expect(picker).toContainText("妈妈");
  expect(state.last).toBe("family");
  await page.goto("/health/family");
  await expect(picker).toHaveCount(0);
});

test("switching members from a generating chat opens a new chat without cancelling the original", async ({ page }) => {
  const state = initialState(); await mockApi(page, state);
  let completed = false;
  await page.route("**/api/conversations/history", route => route.fulfill({ json: {
    session_id: "history", member_id: "shared", member_name: "原共享成员", access_state: "available",
    title: "历史聊天", parent_session_id: null, seed_event_count: 0, fork_available: false,
    records: [], queued_inputs: [], resource_states: [],
    pending_turns: completed ? [] : [{ turn_id: "running", status: "streaming", stream_id: "stream",
      user_message_id: "user", final_assistant_message_id: "assistant",
      created_at: "2026-08-01T12:00:00+08:00", updated_at: "2026-08-01T12:00:00+08:00" }]
  } }));
  await page.route("**/api/conversations/history/streams/stream", route => route.fulfill({
    contentType: "text/event-stream", body: "retry: 60000\n\n"
  }));
  await page.goto("/chat/history");
  await expect(page.getByRole("button", { name: "停止生成", exact: true })).toBeVisible();
  const picker = page.getByRole("button", { name: "选择成员", exact: true });
  await expect(picker).toContainText("原共享成员");
  await picker.click();
  await page.getByRole("option", { name: "妈妈", exact: true }).click();
  await expect(page).toHaveURL(/\/$/);
  await expect(picker).toContainText("妈妈");
  await expect(page.getByRole("textbox", { name: "输入健康问题", exact: true })).toHaveValue("");
  expect(state.last).toBe("family");
  expect(state.requests.filter(path => path.includes("/cancel"))).toEqual([]);
  completed = true;
  await page.goto("/chat/history");
  await expect(picker).toContainText("原共享成员");
  await expect(page.getByRole("button", { name: "停止生成", exact: true })).toHaveCount(0);
});

test("member modal fits a short 300px viewport and refresh retry cannot duplicate creation", async ({ page }) => {
  const state = initialState(); await mockApi(page, state);
  let failRefresh = true;
  await page.route("**/api/members", async route => {
    if (route.request().method() === "GET" && state.members.length === 4 && failRefresh) {
      failRefresh = false;
      return route.fulfill({ status: 503, json: { detail: { message: "暂时无法刷新成员" } } });
    }
    return route.fallback();
  });
  await page.setViewportSize({ width: 300, height: 360 }); await page.goto("/");
  await page.goto("/health/family");
  await page.getByRole("button", { name: "展开侧边栏", exact: true }).click();
  await page.getByRole("button", { name: "切换成员", exact: true }).click();
  await page.getByRole("dialog", { name: "切换成员", exact: true }).getByRole("button", { name: "添加成员", exact: true }).click();
  const dialog = page.getByRole("dialog", { name: "添加成员", exact: true });
  await dialog.locator(".dialog-titlebar").getByRole("button", { name: "返回上一级", exact: true }).click();
  await expect(dialog).toHaveCount(0);
  await page.getByRole("dialog", { name: "切换成员", exact: true }).getByRole("button", { name: "添加成员", exact: true }).click();
  await page.setViewportSize({ width: 390, height: 300 });
  await expect(dialog).toBeVisible();
  const bounds = (await dialog.boundingBox())!;
  expect(bounds.x).toBeGreaterThanOrEqual(0);
  expect(bounds.y).toBeGreaterThanOrEqual(0);
  expect(bounds.x + bounds.width).toBeLessThanOrEqual(390);
  expect(bounds.y + bounds.height).toBeLessThanOrEqual(300);
  await expect(dialog.getByRole("button", { name: "完成", exact: true })).toBeInViewport();

  await dialog.getByLabel("成员名称", { exact: true }).fill("无需重复创建的家人");
  await dialog.getByRole("button", { name: "完成", exact: true }).click();
  await expect(dialog.getByRole("alert")).toContainText("暂时无法刷新成员");
  await expect(dialog.getByRole("button", { name: "完成", exact: true })).toBeEnabled();
  await dialog.getByRole("button", { name: "完成", exact: true }).click();
  await expect(page).toHaveURL(/\/health\/created-/);
  expect(state.requests.filter(request => request === "POST /members")).toHaveLength(1);
});

test(`personal information autosaves and respects read-only access at ${width}px`, async ({ page }) => {
  const state = initialState();
  Object.assign(state.members[1], { sex: "female", birth_date: "1970-03-10", blood_type: "ab" });
  await mockApi(page, state); await page.setViewportSize({ width, height: 900 }); await page.goto("/health/family");
  const identity = page.getByRole("region", { name: "妈妈的健康档案概览", exact: true });
  await expect(identity).toContainText("妈妈");
  await expect(identity).toContainText("女·1970年3月10日·AB 型");
  const nameBox = (await identity.locator('.control-row-title').boundingBox())!;
  const descriptionBox = (await identity.locator('.control-row-description').boundingBox())!;
  expect(descriptionBox.y).toBeGreaterThanOrEqual(nameBox.y + nameBox.height);
  expect(Math.abs(descriptionBox.x - nameBox.x)).toBeLessThan(1);
  const source = identity.getByRole("button", { name: "查看妈妈的个人信息", exact: true });
  await source.click();
  const detail = page.getByRole("region", { name: "个人信息", exact: true });
  await expect(detail).toBeVisible();
  await expect(detail.getByLabel("成员名称", { exact: true })).toHaveValue("妈妈");
  await expect(detail.getByRole("heading", { name: "妈妈", exact: true })).toBeVisible();
  await expect(detail.getByRole("button", { name: "性别", exact: true })).toContainText("女");
  const birthDate = detail.getByRole("button", { name: "出生日期", exact: true });
  await expect(birthDate).toContainText("1970年3月10日");
  await birthDate.click();
  const birthDatePicker = page.getByRole("dialog", { name: "出生日期选择器", exact: true });
  await birthDatePicker.getByLabel("年份", { exact: true }).fill("1971");
  await birthDatePicker.getByLabel("年份", { exact: true }).press("Tab");
  await birthDatePicker.getByRole("button", { name: "完成", exact: true }).click();
  await detail.getByLabel("成员名称", { exact: true }).click();
  await detail.getByRole("button", { name: "血型", exact: true }).click();
  await expect(page.getByRole("option", { name: "O 型", exact: true })).toBeVisible();
  await page.getByRole("option", { name: "O 型", exact: true }).click();
  await detail.getByLabel("成员名称", { exact: true }).fill("母亲");
  await detail.getByRole("button", { name: "返回上一级", exact: true }).click();
  await expect(detail).toHaveCount(0);
  await expect(page.getByRole("button", { name: "查看母亲的个人信息", exact: true })).toBeVisible();
  expect(state.members[1]).toMatchObject({ member_name: "母亲", birth_date: "1971-03-10", blood_type: "o" });
  expect(state.requests.filter(request => request === "PATCH /members/family")).toHaveLength(1);
  await page.goto("/health/shared");
  await page.getByRole("button", { name: "查看owner 本人的个人信息", exact: true }).click();
  await expect(detail).toContainText("来自 owner 的共享健康档案 · 只读");
  await expect(detail.locator("input")).toHaveCount(0);
  await detail.getByRole("button", { name: "返回上一级", exact: true }).click();
  expect(state.requests.filter(request => request === "PATCH /members/shared")).toHaveLength(0);
});

test(`member selection persists and isolates draft at ${width}px`, async ({ page, context }) => {
  const state = initialState(); await mockApi(page, state);
  await page.setViewportSize({ width, height: 900 });
  await page.goto("/");
  const picker = page.locator(".health-member-nav-name");
  await expect(picker).toContainText("妈妈");
  expect(state.requests.indexOf("GET /auth/session")).toBeLessThan(state.requests.indexOf("GET /members"));
  const composer = page.getByRole("textbox", { name: "输入健康问题", exact: true });
  await composer.fill("妈妈的独立草稿");
  await choose(page, "owner 本人 · 来自 owner · 只读");
  await expect(picker).toContainText("owner 本人");
  await newChat(page);
  await expect(composer).toHaveValue("");
  await expect(composer).toBeEnabled();
  expect(state.last).toBe("shared");
  await page.reload(); await expect(picker).toContainText("owner 本人");
  const secondDevice = await context.newPage(); await mockApi(secondDevice, state); await secondDevice.goto("/");
  await expect(secondDevice.locator(".health-member-nav-name")).toContainText("owner 本人");
  await secondDevice.close();

});

test(`revocation silently returns to self and preserves historical binding at ${width}px`, async ({ page }) => {
  const state = initialState(); state.last = "shared"; await mockApi(page, state);
  await page.setViewportSize({ width, height: 900 }); await page.goto("/");
  await expect(page.locator(".health-member-nav-name")).toContainText("owner");
  await page.getByRole("textbox", { name: "输入健康问题", exact: true }).fill("共享档案草稿");
  state.members = state.members.filter(member => member.member_id !== "shared"); state.revision++;
  await page.evaluate(() => window.dispatchEvent(new Event("focus")));
  await expect(page.locator(".health-member-nav-name")).toContainText("本人");
  await expect(page.getByRole("textbox", { name: "输入健康问题", exact: true })).toHaveValue("");
  await expect(page.getByRole("alert")).toHaveCount(0);
  await page.goto("/chat/history");
  await expect(page.getByRole("button", { name: "选择成员" })).toBeEnabled();
  await expect(page.getByRole("textbox", { name: "输入健康问题", exact: true })).toBeDisabled();
  await page.getByRole("button", { name: "选择成员", exact: true }).click();
  await page.getByRole("option", { name: "本人 · 默认成员", exact: true }).click();
  await expect(page).toHaveURL(/\/$/);
  await expect(page.getByRole("textbox", { name: "输入健康问题", exact: true })).toBeEnabled();
});

test("deleted member history opens as an ordinary unassociated conversation", async ({ page }) => {
  const state = initialState();
  await mockApi(page, state);
  await page.route("**/api/conversations/history", route => route.fulfill({ json: {
    session_id: "history", member_id: null, member_name: null, access_state: "available",
    title: "历史聊天", parent_session_id: null, seed_event_count: 0, fork_available: false,
    records: [], pending_turns: [], queued_inputs: [], resource_states: []
  } }));
  await page.goto("/chat/history");
  await expect(page.getByRole("button", { name: "选择成员" })).toBeEnabled();
  await expect(page.getByRole("textbox", { name: "输入健康问题", exact: true })).toBeEnabled();
});

test(`explicit report member overrides startup and read-only controls at ${width}px`, async ({ page }) => {
  const state = initialState(); state.mode = "default"; await mockApi(page, state);
  await page.setViewportSize({ width, height: 900 }); await page.goto("/reports/shared/SAME-ID");
  await expect(page.getByText("shared-报告", { exact: true }).first()).toBeVisible();
  await expect(page.getByRole("button", { name: "删除医疗报告", exact: true })).toBeDisabled();
  await expect(page.getByRole("button", { name: "开始解读", exact: true })).toBeDisabled();
  await expect(page.getByRole("button", { name: "补充原件", exact: true })).toBeDisabled();
  expect(state.requests.some(path => path.includes("/members/self/reports/SAME-ID"))).toBe(false);
  if (width <= 650) {
    await page.getByRole("button", { name: "返回上一级", exact: true }).click();
  }
  await choose(page, "妈妈");
  await expect(page).toHaveURL(/\/health\/family$/);
  await expect(page.getByRole("button", { name: "选择成员" })).toHaveCount(0);
  expect(state.last).toBe("family");
});

test("editable report supplements an original from the inline source action", async ({ page }) => {
  const state = initialState();
  await mockApi(page, state);
  await page.setViewportSize({ width: 1024, height: 900 });
  await page.goto("/reports/self/SAME-ID");

  const supplement = page.getByRole("button", { name: "补充原件", exact: true });
  await expect(supplement).toBeEnabled();
  const chooserPromise = page.waitForEvent("filechooser");
  await supplement.click();
  const chooser = await chooserPromise;
  await chooser.setFiles({
    name: "补充原件.jpg",
    mimeType: "image/jpeg",
    buffer: Buffer.from([0xff, 0xd8, 0xff, 0x01])
  });

  await expect.poll(() => state.requests.filter(
    request => request === "POST /members/self/reports/SAME-ID/source-files"
  ).length).toBe(1);
  await expect(page.getByRole("button", {
    name: "打开原件预览，共 1 个关联文件",
    exact: true
  })).toBeVisible();
  await expect(supplement).toBeEnabled();
  await expect(supplement).toHaveText("补充原件");
  await page.route("**/api/members/self/reports/SAME-ID/source-files/*", route=>route.fulfill({contentType:"text/plain",body:"报告原件内容"}));
  const thumbnail=page.getByRole("button",{name:"打开原件预览，共 1 个关联文件",exact:true});
  await thumbnail.click();
  const preview=page.getByRole("dialog");
  await expect(preview.locator("pre")).toHaveText("报告原件内容");
  await expect(preview.locator(".file-preview-files")).toHaveCount(0);
  await page.keyboard.press("Escape");
  await expect(preview).toHaveCount(0);
  await expect(thumbnail).toBeFocused();
});

test("personal information preserves the draft after a save failure and supports an invited editor", async ({ page }) => {
  const state = initialState();
  Object.assign(state.members[2], { can_edit: true, permission: "edit" });
  await mockApi(page, state);
  let fail = true;
  await page.route("**/api/members/shared", async route => {
    if (route.request().method() === "PATCH" && fail) {
      fail = false;
      return route.fulfill({ status: 503, json: { detail: { message: "暂时无法保存个人信息" } } });
    }
    return route.fallback();
  });
  await page.goto("/health/shared");
  await page.getByRole("button", { name: "查看owner 本人的个人信息", exact: true }).click();
  const detail = page.getByRole("region", { name: "个人信息", exact: true });
  await expect(detail).toContainText("来自 owner 的共享健康档案 · 可编辑");
  await detail.getByLabel("成员名称", { exact: true }).fill("共享家人");
  await expect(detail.getByRole("alert")).toContainText("暂时无法保存个人信息");
  await expect(detail.getByLabel("成员名称", { exact: true })).toHaveValue("共享家人");
  await expect(detail.getByRole("button", { name: "完成", exact: true })).toHaveCount(0);
  expect(state.members[2].member_name).toBe("本人");
  await detail.getByRole("button", { name: "返回上一级", exact: true }).click();
  await expect(detail).toHaveCount(0);
  expect(state.members[2].member_name).toBe("共享家人");
  expect(state.members[0].member_name).toBe("本人");
  await expect(page).toHaveURL(/\/health\/shared$/);
});

test("a failed member switch preserves the original member", async ({ page }) => {
  const state = initialState(); await mockApi(page, state); await page.goto("/health/family");
  await page.route("**/api/account-settings/member-preferences", route => route.fulfill({
    status: 503, json: { detail: { message: "暂时无法切换成员" } }
  }));
  await page.getByRole("button", { name: "切换成员", exact: true }).click();
  const dialog = page.getByRole("dialog", { name: "切换成员", exact: true });
  await dialog.getByRole("button", { name: "本人 · 默认成员", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("暂时无法切换成员");
  await expect(page).toHaveURL(/\/health\/family$/);
  expect(state.last).toBe("family");
  await expect(page.locator(".health-member-nav-name")).toHaveText("妈妈");
});

test(`zero-member workspace stays usable and the first member is forced default at ${width}px`, async ({ page }) => {
  const state = initialState();
  state.members = [];
  state.defaultId = null;
  state.last = null;
  await mockApi(page, state);
  await page.setViewportSize({ width, height: 900 });
  await page.goto("/health/missing");
  await expect(page).toHaveURL(/\/$/);
  await expect(page.getByRole("button", { name: "选择成员" })).toHaveCount(0);
  if (width < 1000) await page.getByRole("button", { name: "展开侧边栏", exact: true }).click();
  const navigation = page.getByRole("complementary", { name: "主导航", exact: true });
  await expect(navigation.locator(".health-member-nav-current")).toHaveCount(0);
  await expect(navigation.getByRole("button", { name: "切换成员", exact: true })).toHaveCount(0);
  await expect(navigation.getByRole("button", { name: "我的收藏", exact: true })).toBeVisible();
  await expect(navigation.getByRole("button", { name: /^账号设置：/ })).toBeVisible();
  expect(state.requests.some(request => request.includes("/reports"))).toBe(false);
  const addMember = navigation.getByRole("button", { name: "添加成员", exact: true });
  await addMember.click();
  const dialog = page.getByRole("dialog", { name: "添加成员", exact: true });
  const defaultSwitch = dialog.getByRole("switch", { name: "设为默认成员" });
  await expect(defaultSwitch).toBeChecked();
  await expect(defaultSwitch).toBeDisabled();
  await dialog.getByLabel("成员名称", { exact: true }).fill("首位成员");
  await dialog.getByRole("button", { name: "完成", exact: true }).click();
  await expect(page).toHaveURL(/\/health\/created-/);
  expect(state.members).toHaveLength(1);
  expect(state.defaultId).toBe(state.members[0].member_id);
});

test("late message response cannot navigate back after member switch", async ({ page }) => {
  const state = initialState(); await mockApi(page, state);
  let release!: () => void;
  const waiting = new Promise<void>(resolve => { release = resolve; });
  let requestedMember = "";
  let finished = false;
  await page.route("**/api/conversations/messages", async route => {
    requestedMember = route.request().postDataJSON().member_id;
    await waiting;
    await route.fulfill({ json: { disposition: "started", session_id: "late-chat", member_id: "family", member_name: "妈妈", title: "迟到响应", turn_id: "turn", user_message_id: "user", final_assistant_message_id: "assistant", model_id: "model", message_status: "queued", stream_id: "stream", content: "", created_at: "2026-08-01T12:00:00+08:00" } });
    finished = true;
  });
  await page.goto("/");
  await page.getByRole("textbox", { name: "输入健康问题", exact: true }).fill("妈妈的问题");
  await page.getByRole("button", { name: "发送", exact: true }).click();
  await expect.poll(() => requestedMember).toBe("family");
  await choose(page, "本人 · 默认成员");
  await expect(page.locator(".health-member-nav-name")).toContainText("本人");
  await newChat(page);
  release();
  await expect.poll(() => finished).toBe(true);
  await expect(page).toHaveURL(/\/$/);
  await expect(page.getByRole("textbox", { name: "输入健康问题", exact: true })).toHaveValue("");
});

test("member switch waits for preference persistence before allowing another selection", async ({ page }) => {
  const state = initialState(); await mockApi(page, state);
  let release!: () => void;
  const waiting = new Promise<void>(resolve => { release = resolve; });
  const writes: string[] = [];
  await page.route("**/api/account-settings/member-preferences", async route => {
    const id = route.request().postDataJSON().last_member_id;
    writes.push(id);
    if (id === "shared") await waiting;
    state.last = id;
    await route.fulfill({ json: {} });
  });
  await page.goto("/");
  await choose(page, "owner 本人 · 来自 owner · 只读");
  await expect.poll(() => writes.length).toBe(1);
  await expect(page.getByRole("dialog", { name: "切换成员", exact: true })
    .getByRole("button", { name: "本人 · 默认成员", exact: true })).toBeDisabled();
  release();
  await expect(page).toHaveURL(/\/health\/shared$/);
  await choose(page, "本人 · 默认成员");
  await expect.poll(() => writes).toEqual(["shared", "self"]);
  await expect(page.locator(".health-member-nav-name")).toContainText("本人");
  expect(state.last).toBe("self");
});

test(`default selection autosaves from personal information at ${width}px`, async ({ page }) => {
  const state = initialState(); await mockApi(page, state);
  await page.setViewportSize({ width, height: 900 }); await page.goto('/health/family');
  const open = () => page.getByRole('button', { name: '查看妈妈的个人信息', exact: true }).click();
  await open();
  const detail = page.getByRole('region', { name: '个人信息', exact: true });
  await expect(detail.getByRole('button', { name: '取消', exact: true })).toHaveCount(0);
  await expect(detail.getByRole('button', { name: '完成', exact: true })).toHaveCount(0);
  await detail.getByRole('switch', { name: '设为默认成员' }).click();
  await detail.getByRole('button', { name: '返回上一级', exact: true }).click();
  await expect(detail).toHaveCount(0);
  expect(state.defaultId).toBe('family');
  expect(state.members.filter(member => member.is_default)).toHaveLength(1);
  await expect(page).toHaveURL(/\/health\/family$/);
  await open();
  await expect(detail.getByRole('switch', { name: '设为默认成员' })).toBeChecked();
  await expect(detail.getByRole('switch', { name: '设为默认成员' })).toBeDisabled();
  await detail.getByRole('button', { name: '返回上一级', exact: true }).click();
});

test(`deleting the initial default preserves a self-created member and navigates to its health page at ${width}px`, async ({ page }) => {
  const state = initialState(); await mockApi(page, state);
  await page.setViewportSize({ width, height: 900 }); await page.goto('/health/self');
  await page.getByRole('button', { name: '查看本人的个人信息', exact: true }).click();
  const detail = page.getByRole('region', { name: '个人信息', exact: true });
  await detail.getByRole('button', { name: '删除成员', exact: true }).click();
  await expect(page).toHaveURL(/\/health\/family$/);
  await expect(detail).toHaveCount(0);
  expect(state.defaultId).toBe('family');
  expect(state.requests.filter(item => item === 'DELETE /members/self')).toHaveLength(1);
  await page.getByRole('button', { name: '查看妈妈的个人信息', exact: true }).click();
  await expect(detail.getByRole('button', { name: '删除成员', exact: true })).toBeEnabled();
  await detail.getByRole('button', { name: '删除成员', exact: true }).click();
  await expect(page).toHaveURL(/\/health\/shared$/);
  expect(state.defaultId).toBe('shared');
});

test('default changes synchronize between windows without moving the current workspace', async ({ page, context }) => {
  const state = initialState(); await mockApi(page, state);
  const other = await context.newPage(); await mockApi(other, state);
  await page.goto('/health/family'); await other.goto('/health/self');
  await page.getByRole('button', { name: '查看妈妈的个人信息', exact: true }).click();
  const detail = page.getByRole('region', { name: '个人信息', exact: true });
  await detail.getByRole('switch', { name: '设为默认成员' }).click();
  await detail.getByRole('button', { name: '返回上一级', exact: true }).click();
  await expect(detail).toHaveCount(0);
  await other.evaluate(() => window.dispatchEvent(new Event('focus')));
  await other.getByRole('button', { name: '切换成员', exact: true }).click();
  const switcher = other.getByRole('dialog', { name: '切换成员', exact: true });
  await expect(switcher.getByRole('button', { name: '妈妈 · 默认成员', exact: true })).not.toHaveAttribute('aria-current');
  await expect(switcher.getByRole('button', { name: '本人', exact: true })).toHaveAttribute('aria-current', 'page');
  await expect(other).toHaveURL(/\/health\/self$/);
  await other.close();
});

test('failed default save keeps the draft and does not change the current default', async ({ page }) => {
  const state = initialState(); await mockApi(page, state);
  await page.route('**/api/members/family', route => route.request().method() === 'PATCH'
    ? route.fulfill({ status: 503, json: { detail: { message: '暂时无法保存成员' } } }) : route.fallback());
  await page.goto('/health/family');
  await page.getByRole('button', { name: '查看妈妈的个人信息', exact: true }).click();
  const detail = page.getByRole('region', { name: '个人信息', exact: true });
  await detail.getByRole('switch', { name: '设为默认成员' }).click();
  await expect(detail.getByRole('alert')).toContainText('暂时无法保存成员');
  await expect(detail.getByRole('switch', { name: '设为默认成员' })).toBeChecked();
  expect(state.defaultId).toBe('self');
  expect(state.members[1].is_default).toBe(false);
  await detail.getByRole('button', { name: '返回上一级', exact: true }).click();
  await expect(detail).toBeVisible();
});

for (const width of [390, 820, 1280]) {
  test(`report navigation keeps the health archive at ${width}px`, async ({ page }) => {
    const state = initialState();
    await mockApi(page, state);
    await page.route("**/api/members/family/reports", route => route.fulfill({ json: {
      reports: [{ report_id: "SAME-ID", member_id: "family", report_type: "其它医疗报告", report_name: "family-报告", report_time: "2026-08-01T12:00:00+08:00", flagged_count: 0 }], total: 1
    } }));
    await page.setViewportSize({ width, height: 900 });
    await page.goto("/health/family");
    const overview = page.getByRole("region", { name: "妈妈的健康档案概览", exact: true });
    await expect(overview).toBeVisible();
    await page.getByRole("button", { name: "打开医疗报告：family-报告", exact: true }).click();
    await expect(page).toHaveURL(/\/reports\/family\/SAME-ID$/);
    await expect(page.locator(".report-detail-column")).toBeVisible();
    await expect(page.locator(".reports-list-toolbar")).toHaveText("健康档案");
    if (width <= 650) {
      await page.locator(".reports-detail-toolbar").getByRole("button", { name: "返回上一级" }).click();
      await expect(page).toHaveURL(/\/health\/family$/);
      await expect(overview).toBeVisible();
      await expect(page.getByRole("button", { name: "创建医疗报告", exact: true })).toBeVisible();
    } else {
      await expect(overview).toBeVisible();
    }
    await page.goto("/reports/family/SAME-ID");
    await expect(page.locator(".report-detail-column")).toBeVisible();
    await expect(page.locator(".reports-list-toolbar")).toHaveText("健康档案");
    await page.setViewportSize({ width: 390, height: 900 });
    await page.locator(".reports-detail-toolbar").getByRole("button", { name: "返回上一级" }).click();
    await expect(page).toHaveURL(/\/health\/family$/);
    await expect(overview).toBeVisible();
    await expect(page.locator(".health-member-sections button")).toHaveCount(4);
  });
}


test("medical history failure retains draft, retries latest text and never changes another member", async ({ page }) => {
  const state = initialState();
  await mockApi(page, state);
  let fail = true;
  await page.route("**/api/members/family/medical-history", async route => {
    if (route.request().method() === "PATCH" && fail) return route.fulfill({ status: 503, json: { detail: { message: "既往史保存暂时失败" } } });
    return route.fallback();
  });
  await page.goto("/health/family");
  await page.getByRole("button", { name: "查看妈妈的个人信息", exact: true }).click();
  const history = page.getByRole("region", { name: "既往史", exact: true });
  const field = history.getByRole("textbox", { name: "过敏史", exact: true });
  await field.fill("待保存内容");
  await expect(history.getByRole("alert")).toContainText("既往史保存暂时失败");
  await expect(field).toHaveValue("待保存内容");
  fail = false;
  await field.fill("明确修正内容");
  await expect.poll(() => state.histories.family?.allergy_history.text).toBe("明确修正内容");
  await page.goto("/health/self");
  await page.getByRole("button", { name: "查看本人的个人信息", exact: true }).click();
  await expect(history.getByRole("textbox", { name: "过敏史", exact: true })).toHaveValue("");
  await page.goto("/health/shared");
  await page.getByRole("button", { name: "查看owner 本人的个人信息", exact: true }).click();
  await expect(history.getByText("未记录", { exact: true })).toHaveCount(8);
  await expect(history.getByRole("textbox")).toHaveCount(0);
});

test("failed member deletion preserves pending history and composition saves only committed text", async ({ page }) => {
  const state = initialState();
  await mockApi(page, state);
  await page.route("**/api/members/family", async route => {
    if (route.request().method() === "DELETE") return route.fulfill({ status: 503, json: { detail: { message: "删除暂时失败" } } });
    return route.fallback();
  });
  await page.goto("/health/family");
  await page.getByRole("button", { name: "查看妈妈的个人信息", exact: true }).click();
  const field = page.getByRole("region", { name: "既往史", exact: true }).getByRole("textbox", { name: "过敏史", exact: true });
  await field.dispatchEvent("compositionstart");
  await field.fill("中文输入中");
  await page.waitForTimeout(500);
  expect(state.requests.filter(value => value === "PATCH /members/family/medical-history")).toHaveLength(0);
  await field.dispatchEvent("compositionend");
  await page.getByRole("button", { name: "删除成员", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("删除暂时失败");
  await expect.poll(() => state.histories.family?.allergy_history.text).toBe("中文输入中");
  await expect(field).toHaveValue("中文输入中");
});

for (const destination of ["page", "member", "log-list"] as const) {
  test(`medical history blocks ${destination} navigation on save failure and retries before leaving`, async ({ page }) => {
    const state = initialState();
    await mockApi(page, state);
    await page.route("**/api/members/family/medical-logs**", route => route.fulfill({ json: { member_id: "family", medical_logs: [] } }));
    let fail = true;
    let attempts = 0;
    await page.route("**/api/members/family/medical-history", async route => {
      if (route.request().method() === "PATCH") {
        attempts++;
        if (fail) return route.fulfill({ status: 503, json: { detail: { message: "既往史保存暂时失败" } } });
      }
      return route.fallback();
    });
    const path = destination === "log-list" ? "/health/family/medical-logs" : "/health/family";
    await page.goto(path);
    await page.getByRole("button", { name: "查看妈妈的个人信息", exact: true }).click();
    const history = page.getByRole("region", { name: "既往史", exact: true });
    const field = history.getByRole("textbox", { name: "过敏史", exact: true });
    await field.fill("离开前需要保存的内容");
    await expect(history.getByRole("alert")).toContainText("既往史保存暂时失败");
    const leave = async () => {
      if (destination === "member") await choose(page, "本人 · 默认成员");
      else await page.getByRole("button", { name: destination === "page" ? "我的收藏" : "健康日记", exact: true }).click();
    };
    const previousAttempts = attempts;
    await leave();
    await expect.poll(() => attempts).toBeGreaterThan(previousAttempts);
    await expect(page).toHaveURL(path);
    await expect(field).toHaveValue("离开前需要保存的内容");
    await expect(field).toBeEnabled();
    fail = false;
    await leave();
    await expect.poll(() => state.histories.family?.allergy_history.text).toBe("离开前需要保存的内容");
    await expect(history).toHaveCount(0);
    expect(state.histories.self?.allergy_history.text ?? null).toBeNull();
  });
}

test("medical history follows group spacing and grows and shrinks when the viewport changes", async ({ page }) => {
  const state = initialState();
  const text = "用于验证自动换行与完整显示的既往史测试内容。".repeat(30);
  state.histories.family = Object.fromEntries(MEDICAL_HISTORY_FIELDS.map(([field]) => [field, { text: field === "past_medical_history" ? text : null, updated_at: null }]));
  await mockApi(page, state);
  await page.goto("/health/family");
  await page.getByRole("button", { name: "查看妈妈的个人信息", exact: true }).click();
  const history = page.getByRole("region", { name: "既往史", exact: true });
  const field = history.getByRole("textbox", { name: "既往疾病史", exact: true });
  await expect(field).toHaveValue(text);
  const gaps = await page.locator(".member-information-scroll").evaluate(pane => {
    const base = pane.children[0].getBoundingClientRect();
    const heading = pane.querySelector(".group-heading")!.getBoundingClientRect();
    const list = pane.querySelector(".member-history .grouped-object-list")!.getBoundingClientRect();
    return [heading.top - base.bottom, list.top - heading.bottom];
  });
  expect(gaps).toEqual([15, 5]);
  const overflow = () => field.evaluate(area => area.scrollHeight - area.clientHeight);
  await expect.poll(overflow).toBeLessThanOrEqual(1);
  const height = await field.evaluate(area => area.clientHeight);
  await page.setViewportSize({ width: 390, height: 844 });
  await expect.poll(overflow).toBeLessThanOrEqual(1);
  await expect.poll(() => field.evaluate(area => area.clientHeight)).toBeGreaterThan(height);
  await page.setViewportSize({ width: 1280, height: 900 });
  await expect.poll(() => field.evaluate(area => area.clientHeight)).toBe(height);
});

test("read-only medical history aligns short values to the left and wraps long text", async ({ page }) => {
  const state = initialState();
  state.histories.shared = Object.fromEntries(MEDICAL_HISTORY_FIELDS.map(([field]) => [field, {
    text: field === "past_medical_history" ? "只读长文本换行测试。".repeat(30) : "不详", updated_at: null
  }]));
  await mockApi(page, state);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/health/shared");
  await page.getByRole("button", { name: "查看owner 本人的个人信息", exact: true }).click();
  const history = page.getByRole("region", { name: "既往史", exact: true });
  await expect(history.getByRole("textbox")).toHaveCount(0);
  const positions = await history.locator(".field-value").evaluateAll(values => values.map(value => {
    const range = document.createRange();
    range.setStart(value.firstChild!, 0);
    range.setEnd(value.firstChild!, 1);
    return { offset: range.getBoundingClientRect().left - value.getBoundingClientRect().left, overflow: value.scrollHeight - value.clientHeight };
  }));
  expect(positions).toHaveLength(8);
  for (const position of positions) {
    expect(Math.abs(position.offset)).toBeLessThanOrEqual(1);
    expect(position.overflow).toBeLessThanOrEqual(1);
  }
});


test('birth date offers today and unknown without long-term and preserves an empty date', async ({page}) => {
 const state = initialState();
 await mockApi(page, state);
 await page.clock.setFixedTime(new Date('2026-09-08T12:05:00'));
 await page.goto('/health/family');
 await page.getByRole('button',{name:'查看妈妈的个人信息',exact:true}).click();
 const trigger = page.getByRole('button',{name:'出生日期',exact:true});
 const picker = page.getByRole('dialog',{name:'出生日期选择器',exact:true});
 await trigger.click();
 await expect(picker.getByRole('button',{name:'长期',exact:true})).toHaveCount(0);
 await picker.getByRole('button',{name:'今天',exact:true}).click();
 await picker.getByRole('button',{name:'完成',exact:true}).click();
 await expect.poll(() => state.members[1].birth_date).toBe('2026-09-08');
 await trigger.click();
 await picker.getByRole('button',{name:'未知',exact:true}).click();
 await expect(trigger).toHaveText('未知');
 await expect.poll(() => state.members[1].birth_date).toBeNull();
 await page.reload();
 await page.getByRole('button',{name:'查看妈妈的个人信息',exact:true}).click();
 await trigger.click();
 await expect(picker.getByRole('button',{name:'未知',exact:true})).toHaveAttribute('aria-pressed','true');
 await expect(picker.locator('[aria-selected="true"]')).toHaveCount(0);
 await page.getByLabel('成员名称',{exact:true}).click();
 await expect(picker).toHaveCount(0);
 await expect(page.getByLabel('成员名称',{exact:true})).toBeFocused();
 expect(state.members[1].birth_date).toBeNull();
});
