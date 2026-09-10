import { expect, test } from "@playwright/test";
import { mockWorkspace } from "../helpers/workspace";
import type { BodyRecord } from "../../src/api/bodyMetricApi";

const record: BodyRecord = {
  record_id: "record",
  member_id: "self",
  kind: "meal",
  metric: "",
  starts_at: "2026-11-01T06:30:32.123456+00:00",
  ends_at: null,
  timezone: "UTC",
  precision: "instant",
  source: "test",
  device: "",
  origin: "manual",
  notes: "",
  data: { energy: 100, foods: [] },
  import_managed: false,
  edited: false,
  created_at: "",
  updated_at: "",
  files: [],
};

for (const timezoneId of [
  "UTC",
  "Asia/Shanghai",
  "Asia/Kolkata",
  "America/New_York",
]) {
  test.describe(timezoneId, () => {
    test.use({ timezoneId, viewport: { width: 390, height: 520 } });
    test("opening and reselecting a date preserves the exact instant", async ({
      page,
    }) => {
      await mockWorkspace(page);
      let submitted: Partial<BodyRecord> | undefined;
      await page.route("**/api/members/self/body-metrics/**", (route) => {
        const path = new URL(route.request().url()).pathname;
        if (route.request().method() === "PATCH") {
          submitted = route.request().postDataJSON();
          return route.fulfill({ json: { ...record, ...submitted } });
        }
        return route.fulfill({
          json: path.endsWith("/catalog")
            ? { metrics: [], meal_types: { breakfast: "早餐" }, stages: {} }
            : path.endsWith("/records/record")
              ? record
              : path.endsWith("/records")
                ? { items: [], total: 0, next_offset: null }
                : {
                    series: [],
                    sources: [],
                    total_records: 0,
                    coverage_from: null,
                    coverage_to: null,
                  },
        });
      });
      await page.goto("/health/self/body-metrics/nutrition?record=record");
      const editor = page.getByRole("dialog", {
        name: "待补充分餐",
        exact: true,
      });
      const dateButton = editor
        .locator(".field-row")
        .filter({ has: page.getByText("发生时间", { exact: true }) })
        .getByRole("button");
      for (const reselect of [false, true]) {
        await dateButton.click();
        const picker = page.getByRole("dialog", {
          name: "发生时间选择器",
          exact: true,
        });
        if (reselect)
          await picker.getByRole("gridcell", { selected: true }).click();
        await picker.getByRole("button", { name: "完成", exact: true }).click();
      }
      await editor
        .getByRole("button", { name: "保存记录", exact: true })
        .click();
      await expect.poll(() => submitted?.starts_at).toBe(record.starts_at);
    });
  });
}

test("partial image upload retains the created record and only retries remaining images", async ({
  page,
}) => {
  await mockWorkspace(page);
  let creates = 0,
    uploadCount = 0;
  let release: (() => void) | undefined;
  await page.route("**/api/members/self/body-metrics/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    const method = route.request().method();
    if (method === "POST" && path.endsWith("/records")) {
      creates++;
      await new Promise<void>((resolve) => {
        release = resolve;
      });
      return route.fulfill({
        json: { ...record, ...route.request().postDataJSON() },
      });
    }
    if (method === "POST" && path.endsWith("/files")) {
      uploadCount++;
      return uploadCount === 2
        ? route.fulfill({
            status: 503,
            json: { detail: { message: "第二张图片未保存，请重试" } },
          })
        : route.fulfill({ json: record });
    }
    if (method === "PATCH") return route.fulfill({ json: record });
    return route.fulfill({
      json: path.endsWith("/catalog")
        ? { metrics: [], meal_types: { breakfast: "早餐" }, stages: {} }
        : path.endsWith("/records")
          ? { items: [], total: 0, next_offset: null }
          : { series: [], sources: [], total_records: 0 },
    });
  });
  await page.goto("/health/self/body-metrics/nutrition");
  await page.getByRole("button", { name: "＋ 创建记录", exact: true }).click();
  const editor = page.getByRole("dialog", {
    name: "创建记录",
    exact: true,
  });
  await editor.locator('input[type="file"]').setInputFiles([
    { name: "first.png", mimeType: "image/png", buffer: Buffer.from("first") },
    {
      name: "second.png",
      mimeType: "image/png",
      buffer: Buffer.from("second"),
    },
  ]);
  await editor.getByRole("button", { name: "完成", exact: true }).click();
  await expect.poll(() => creates).toBe(1);
  await expect(
    editor.getByRole("button", { name: "＋ 添加食物", exact: true }),
  ).toBeDisabled();
  await expect(editor.locator('input[type="file"]')).toBeDisabled();
  release!();
  await expect(editor.getByRole("alert")).toContainText("第二张图片未保存");
  await editor.getByRole("button", { name: "完成", exact: true }).click();
  await expect(editor).toHaveCount(0);
  expect(creates).toBe(1);
  expect(uploadCount).toBe(3);
});

test('body import history loads bounded pages and retains the first page when loading more',async({page})=>{
 await mockWorkspace(page);const queries:string[]=[];
 await page.route('**/api/members/self/body-metrics/**',route=>{
  const url=new URL(route.request().url());
  if(url.pathname.endsWith('/imports')){
   queries.push(url.search);const next=url.searchParams.get('cursor');
   return route.fulfill({json:{items:[{import_id:next?'older':'newer',filename:next?'older.json':'newer.json',state:'completed'}],next_cursor:next?null:'cursor-page-2',has_more:!next}});
  }
  if(url.pathname.endsWith('/catalog'))return route.fulfill({json:{metrics:[],meal_types:{},stages:{}}});
  if(url.pathname.endsWith('/records'))return route.fulfill({json:{items:[],total:0,next_offset:null}});
  return route.fulfill({json:{series:[],sources:[],total_records:0,coverage_from:null,coverage_to:null}});
 });
 await page.goto('/health/self/body-metrics');await page.getByRole('button',{name:'导入身体指标',exact:true}).click();
 const dialog=page.getByRole('dialog',{name:'导入身体指标',exact:true});
 await expect(dialog.getByRole('button',{name:/newer.json/})).toBeVisible();
 await dialog.getByRole('button',{name:'加载更多导入记录',exact:true}).click();
 await expect(dialog.getByRole('button',{name:/older.json/})).toBeVisible();await expect(dialog.getByRole('button',{name:/newer.json/})).toBeVisible();
 await expect(dialog.getByRole('button',{name:'加载更多导入记录',exact:true})).toHaveCount(0);
 expect([...new Set(queries)]).toEqual(['?limit=24','?limit=24&cursor=cursor-page-2']);
});
