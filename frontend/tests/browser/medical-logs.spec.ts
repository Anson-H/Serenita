import { expect, test } from "@playwright/test";
import { mockWorkspace } from "../helpers/workspace";
import {expectSelectionReplacement} from '../helpers/selectionSpacing';

const first = { medical_log_id: "first", member_id: "self", recorded_on: "2026-09-01", title: "早期经历补记", content: "家属描述可能出现头痛", created_at: "2026-09-01T10:00:00+08:00", updated_at: "2026-09-01T10:00:00+08:00" };
const second = { ...first, medical_log_id: "second", title: "复诊后续", recorded_on: "2026-09-02" };

async function mockLogs(page: Parameters<typeof mockWorkspace>[0]) {
  await mockWorkspace(page);
  await page.route("**/api/members/self/medical-logs**", route => {
    const url = new URL(route.request().url());
    if (url.pathname.endsWith("/first")) return route.fulfill({ json: { medical_log: first } });
    if (url.pathname.endsWith("/second")) return route.fulfill({ json: { medical_log: second } });
    const rows = [second, first];
    return route.fulfill({ json: { member_id: "self", medical_logs: rows.map(log => ({ ...log, summary: log.content })) } });
  });
}

test("read-only logs expose complete content and no mutation controls", async ({ page }) => {
  await mockLogs(page);
  await page.route("**/api/members", route => route.fulfill({ json: { access_revision: 1, default_member_id: "self", initial_member_id: "self", last_member_id: "self", startup_mode: "last_used", members: [{ member_id: "self", member_name: "家人", account_id: "owner", owner_account: "owner", is_owned: false, can_edit: false, permission: "read" }] } }));
  await page.goto("/health/self/medical-logs/first");
  await expect(page.locator(".medical-log-content")).toHaveText(first.content);
  await expect(page.locator('.object-list-count')).toHaveText('共 2 条健康日记');
  await expect(page.getByRole("button", { name: "创建健康日记", exact: true })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "删除日记", exact: true })).toHaveCount(0);
  await expect(page.getByLabel("日记内容", { exact: true })).toHaveCount(0);
});

test("log count shows the full total before and after loading more", async ({ page }) => {
  await mockLogs(page);
  await page.route("**/api/members/self/medical-logs?*", route => {
    const next = new URL(route.request().url()).searchParams.get("cursor") === "next";
    const rows = next ? [first] : [second];
    return route.fulfill({ json: { member_id: "self", medical_logs: rows.map(log => ({ ...log, summary: log.content })), total: 2, next_cursor: next ? null : "next" } });
  });
  await page.goto("/health/self/medical-logs");
  const rows = page.locator(".report-timeline-item");
  const count = page.locator(".object-list-count");
  await expect(rows).toHaveCount(1);
  await expect(count).toHaveText("共 2 条健康日记");
  await page.getByRole("button", { name: "加载更多健康日记", exact: true }).click();
  await expect(rows).toHaveCount(2);
  await expect(count).toHaveText("共 2 条健康日记");
  await expect(page.getByRole("button", { name: "加载更多健康日记", exact: true })).toHaveCount(0);
});

test("late detail response cannot overwrite another log", async ({ page }) => {
  await mockLogs(page);
  let release!: () => void;
  const pending = new Promise<void>(resolve => { release = resolve; });
  await page.route("**/api/members/self/medical-logs/first", async route => {
    await pending;
    await route.fulfill({ json: { medical_log: first } });
  });
  await page.goto("/health/self/medical-logs/first");
  await page.getByRole("button", { name: /复诊后续/ }).click();
  await expect(page.getByLabel("日记标题", { exact: true })).toHaveValue(second.title);
  release();
  await expect(page.getByLabel("日记标题", { exact: true })).toHaveValue(second.title);
  await expect(page.getByRole("button", { name: "日期", exact: true })).toContainText("2026年9月2日");
});

test("failed refresh preserves an unsaved editor draft", async ({ page }) => {
  await mockLogs(page);
  await page.goto("/health/self/medical-logs/first");
  await expect(page.getByLabel("日记标题", { exact: true })).toHaveValue(first.title);
  await page.route("**/api/members/self/medical-logs/first", route => route.fulfill({ status: 503, json: { detail: { message: "临时不可用" } } }));
  await page.getByLabel("日记内容", { exact: true }).fill("用户补充但尚未保存的内容");
  await expect(page.getByRole("button", { name: "重试保存" })).toBeVisible();
  await page.evaluate(() => window.dispatchEvent(new Event("focus")));
  await expect(page.locator(".medical-log-form").getByText("临时不可用", { exact: true }).first()).toBeVisible();
  await expect(page.getByLabel("日记内容", { exact: true })).toHaveValue("用户补充但尚未保存的内容");
});

test("log prose stays fully visible when the detail column narrows", async ({ page }) => {
  await mockLogs(page);
  const content = "家属描述：前几天可能有发热，具体日期不清楚。随后到门诊就医。\n\n用户转述：今天体温有所下降，食欲比昨天好，偶尔仍有咳嗽。";
  await page.route("**/api/members/self/medical-logs/first", route => route.fulfill({ json: { medical_log: { ...first, content } } }));
  await page.goto("/health/self/medical-logs/first");
  const body = page.getByLabel("日记内容", { exact: true });
  await expect(body).toHaveValue(content);
  const overflow = () => body.evaluate(area => area.scrollHeight - area.clientHeight);
  await expect.poll(overflow).toBeLessThanOrEqual(1);
  await page.setViewportSize({ width: 390, height: 844 });
  await expect.poll(overflow).toBeLessThanOrEqual(1);
  await expect(body).toHaveValue(content);
  await expect(page.getByRole("button", { name: "删除日记", exact: true })).toBeVisible();
});


test("log context deletion waits for autosave and clears the open detail", async ({ page }) => {
  await mockLogs(page);
  let current = { ...first };
  let removed = false;
  const calls: string[] = [];
  let release!: () => void;
  const saving = new Promise<void>(resolve => { release = resolve; });
  await page.route("**/api/members/self/medical-logs**", async route => {
    if (new URL(route.request().url()).pathname.endsWith("/first")) {
      if (route.request().method() === "PATCH") {
        calls.push("save-start");
        await saving;
        current = { ...current, ...route.request().postDataJSON() };
        calls.push("save-end");
      }
      if (route.request().method() === "DELETE") {
        calls.push("delete"); removed = true;
        return route.fulfill({ json: { deleted: true } });
      }
      return route.fulfill({ json: { medical_log: current } });
    }
    return route.fulfill({ json: { medical_logs: (removed ? [second] : [second, current]).map(log => ({ ...log, summary: log.content })) } });
  });
  await page.goto("/health/self/medical-logs/first");
  await page.getByLabel("日记内容", { exact: true }).fill("正在保存的补充");
  await expect.poll(() => calls).toEqual(["save-start"]);
  await page.getByRole("button", { name: /早期经历补记/ }).click({ button: "right" });
  await page.getByRole("menuitem", { name: "删除", exact: true }).click();
  expect(calls).toEqual(["save-start"]);
  release();
  await expect(page).toHaveURL(/\/medical-logs$/);
  await expect(page.getByRole("button", { name: /早期经历补记/ })).toHaveCount(0);
  expect(calls).toEqual(["save-start", "save-end", "delete"]);
});

test("batch log deletion retains failed selections and retries only those logs", async ({ page }) => {
  await mockLogs(page);
  let rows = [second, first];
  let fail = true;
  const deletes: string[] = [];
  await page.route("**/api/members/self/medical-logs**", route => {
    const id = new URL(route.request().url()).pathname.split("/").pop()!;
    if (route.request().method() === "DELETE") {
      deletes.push(id);
      if (id === "first" && fail) return route.fulfill({ status: 503, json: { detail: { message: "删除暂时失败" } } });
      rows = rows.filter(log => log.medical_log_id !== id);
      return route.fulfill({ json: { deleted: true } });
    }
    return route.fulfill({ json: { medical_logs: rows.map(log => ({ ...log, summary: log.content })) } });
  });
  await page.goto("/health/self/medical-logs");
  const row = page.getByRole("button", { name: /复诊后续/ });
  const originalRowY=(await row.boundingBox())!.y;
  await row.focus(); await page.keyboard.press("Shift+F10");
  await page.getByRole("menuitem", { name: "多选", exact: true }).click();
  await expectSelectionReplacement(page.locator('.report-library .list-selection-heading'),page.locator('.medical-log-filters'));
  expect((await page.getByRole('checkbox',{name:/复诊后续/}).boundingBox())!.y).toBeCloseTo(originalRowY,0);
  await page.getByRole("button", { name: "全选健康日记", exact: true }).click();
  await page.getByRole("button", { name: "删除", exact: true }).click();
  await expect(page.getByRole("checkbox", { name: /早期经历补记/ })).toBeChecked();
  await expect(page.getByRole("checkbox", { name: /复诊后续/ })).toHaveCount(0);
  fail = false;
  await page.getByRole("button", { name: "删除", exact: true }).click();
  await expect(page.getByRole("button", { name: "创建健康日记", exact: true })).toBeVisible();
  expect(deletes).toEqual(["second", "first", "first"]);
});




for(const width of [1280,390])test(`new logs default to the local record date and cannot clear it at ${width}px`, async ({ page },testInfo) => {
  await page.setViewportSize({width,height:900});
  await mockLogs(page);
  await page.goto("/health/self/medical-logs");
  await page.getByRole("button", { name: "创建健康日记", exact: true }).click();
  await expect(page.getByRole("dialog",{name:"创建健康日记",exact:true})).toHaveAttribute("aria-modal","true");
  const dialog=page.getByRole("dialog",{name:"创建健康日记",exact:true});
  const frame=(await dialog.boundingBox())!,header=(await dialog.locator('.dialog-titlebar').boundingBox())!;
  expect(Math.abs(frame.y-header.y)).toBeLessThan(2);
  await dialog.screenshot({path:testInfo.outputPath(`log-create-${width}.png`)});
  const today = await page.evaluate(() => {
    const now = new Date();
    return `${now.getFullYear()}年${now.getMonth() + 1}月${now.getDate()}日`;
  });
  await expect(page.getByRole("button", { name: "日期", exact: true })).toHaveText(today);
  await expect(page.getByRole("button", { name: "清空日期", exact: true })).toHaveCount(0);
  await page.getByRole("button", { name: "日期", exact: true }).click();
  await page.getByRole("textbox", { name: "年份", exact: true }).fill("");
  await expect(page.getByRole("dialog", { name: "日期选择器", exact: true }).getByRole("button", { name: "完成", exact: true })).toBeDisabled();
});

test('dismissing a failed autosave notification does not retry on blur or block the mobile back control',async({page})=>{
 await mockLogs(page);await page.setViewportSize({width:390,height:700});let writes=0;
 await page.route('**/api/members/self/medical-logs/first',route=>{
  if(route.request().method()==='PATCH'){writes++;return route.fulfill({status:503,json:{detail:{message:'保留失败草稿'}}});}
  return route.fulfill({json:{medical_log:first}});
 });
 await page.goto('/health/self/medical-logs/first');await page.getByLabel('日记标题',{exact:true}).fill('失败草稿');
 await expect(page.getByRole('button',{name:'重试保存',exact:true})).toBeVisible();
 await page.getByRole('button',{name:'关闭通知',exact:true}).click();
 await expect(page.getByRole('complementary',{name:'状态通知'})).toHaveCount(0);expect(writes).toBe(1);
 await page.locator('.medical-log-detail').getByRole('button',{name:'返回上一级',exact:true}).click();
 await expect(page).toHaveURL(/medical-logs\/first$/);await expect(page.getByLabel('日记标题',{exact:true})).toHaveValue('失败草稿');
});

for (const width of [1280, 390]) test(`log detail edits only its own fields at ${width}px`, async ({ page }) => {
  await page.setViewportSize({ width, height: 900 });
  await mockLogs(page);
  let current = { ...first };
  const patches: unknown[] = [];
  await page.route("**/api/members/self/medical-logs/first", route => {
    if (route.request().method() === "PATCH") {
      const changes = route.request().postDataJSON();
      patches.push(changes);
      current = { ...current, ...changes };
    }
    return route.fulfill({ json: { medical_log: current } });
  });
  await page.goto("/health/self/medical-logs/first");
  await expect(page.getByLabel("日记内容", { exact: true })).toHaveValue(first.content);
  await expect(page.getByRole("heading", { name: "关联医疗报告", exact: true })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "添加关联医疗报告", exact: true })).toHaveCount(0);
  await page.getByLabel("日记内容", { exact: true }).fill("今天症状好转");
  await expect.poll(() => patches).toEqual([{ content: "今天症状好转" }]);
  await page.reload();
  await expect(page.getByLabel("日记内容", { exact: true })).toHaveValue("今天症状好转");
});
