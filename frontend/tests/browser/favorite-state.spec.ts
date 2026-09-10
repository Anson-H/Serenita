import { expect, test, type Page } from "@playwright/test";
import type { Favorite } from "../../src/api/types";

function favorite(id: string, title: string, tags: string[]): Favorite {
  return {
    content_snapshot: `${title} 的完整内容`,
    content_summary: `${title} 的摘要`,
    created_at: "2026-09-04T10:00:00+08:00",
    favorite_id: id,
    member_id: null,
    member_name: null,
    source_available: true,
    source_id: `message-${id}`,
    source_session_id: `session-${id}`,
    source_type: "message",
    tags,
    title,
    updated_at: "2026-09-04T10:00:00+08:00"
  };
}

type FavoriteApiState = {
  favorites: Favorite[];
  patchBodies: string[][];
  waitForFirstDetail?: Promise<void>;
  waitForFirstPatch?: Promise<void>;
};

async function mockFavoriteWorkspace(page: Page, state: FavoriteApiState) {
  await page.route(url => url.pathname.startsWith("/api/"), async route => {
    const request = route.request();
    const path = new URL(request.url()).pathname.slice(4);
    const method = request.method();
    const json = (value: unknown, status = 200) => route.fulfill({ json: value, status });
    if (path === "/conversations/attachment-capabilities") return json({ model_id: new URL(route.request().url()).searchParams.get("model_id"), file_mime_types: ["image/jpeg", "image/png", "application/pdf"] });
    if (path === "/auth/session") {
      return json({
        authenticated: true,
        account: "favorite-test",
        account_id: "favorite-test-id",
        expires_at: "2099-01-01T00:00:00+08:00",
        account_name: "收藏测试"
      });
    }
    if (path === "/members/access-events") {
      return route.fulfill({ body: "retry: 60000\n\n", contentType: "text/event-stream" });
    }
    if (path === "/members") {
      return json({ access_revision: 1, default_member_id: null, initial_member_id: null,
        last_member_id: null, members: [], startup_mode: "last_used" });
    }
    if (path === "/conversations") return json({ sessions: [], has_more: false, next_cursor: null });
    if (path === "/favorites" && method === "GET") {
      return json({ favorites: state.favorites, has_more: false, next_cursor: null });
    }
    if (path.startsWith("/favorites/") && method === "GET") {
      const id = path.split("/")[2];
      if (id === "a" && state.waitForFirstDetail) await state.waitForFirstDetail;
      return json(state.favorites.find(item => item.favorite_id === id));
    }
    if (path.startsWith("/favorites/") && method === "PATCH") {
      const id = path.split("/")[2];
      const tags = request.postDataJSON().tags as string[];
      state.patchBodies.push(tags);
      if (state.patchBodies.length === 1 && state.waitForFirstPatch) await state.waitForFirstPatch;
      const current = state.favorites.find(item => item.favorite_id === id)!;
      current.tags = [...tags];
      current.updated_at = `2026-09-04T10:00:0${state.patchBodies.length}+08:00`;
      return json({ ...current, tags: [...tags] });
    }
    if (path === "/models") return json({ models: [] });
    if (path === "/model-providers") return json({ providers: [] });
    if (path === "/model-access-settings") {
      return json({ defaults: { chat: null, compact: null, title: null, vision_parse: null } });
    }
    if (path === "/account-settings/conversation-preferences") {
      return json({
        composer_submit_shortcut: "enter",
        base_context_display_modes: {
          system_prompt: "conversation_start",
          tool_catalog: "conversation_start",
          skill_catalog: "conversation_start",
          runtime_context: "conversation_start"
        },
        is_context_window_usage_visible: false,
        is_related_content_visible: true,
        is_token_usage_visible: false,
        visible_context_types: [],
        tool_display_types: ["model_tool_request", "tool_call"]
      });
    }
    return json({ detail: { message: `未模拟 ${method} ${path}` } }, 404);
  });
}

test("a late favorite detail response cannot replace the latest selection", async ({ page }) => {
  let releaseFirstDetail: () => void = () => {};
  const waitForFirstDetail = new Promise<void>(resolve => { releaseFirstDetail = resolve; });
  const state: FavoriteApiState = {
    favorites: [favorite("a", "收藏 A", []), favorite("b", "收藏 B", [])],
    patchBodies: [],
    waitForFirstDetail
  };
  await mockFavoriteWorkspace(page, state);
  await page.goto("/favorites");
  await expect(page.getByText("未关联成员 · AI 回答", { exact: true })).toHaveCount(2);

  const firstRequest = page.waitForRequest(request => request.url().endsWith("/api/favorites/a"));
  await page.getByRole("button", { name: "查看收藏：收藏 A", exact: true }).click();
  await firstRequest;
  await page.getByRole("button", { name: "查看收藏：收藏 B", exact: true }).click();
  await expect(page.locator(".favorites-detail-toolbar")).toContainText("收藏 B");
  const completed = page.waitForResponse(response => response.url().endsWith("/api/favorites/a"));
  releaseFirstDetail();
  await (await completed).finished();
  await page.evaluate(() => new Promise<void>(resolve => requestAnimationFrame(() => requestAnimationFrame(() => resolve()))));
  await expect(page.locator(".favorites-detail-toolbar")).toContainText("收藏 B");
  await expect(page.getByRole("complementary", { name: "收藏详情", exact: true })).toContainText("收藏 B 的完整内容");
});

test("favorite tag saves serialize per favorite without rewinding a newer draft", async ({ page }) => {
  let releaseFirstPatch: () => void = () => {};
  const waitForFirstPatch = new Promise<void>(resolve => { releaseFirstPatch = resolve; });
  const state: FavoriteApiState = {
    favorites: [favorite("a", "收藏 A", ["初始"])],
    patchBodies: [],
    waitForFirstPatch
  };
  await mockFavoriteWorkspace(page, state);
  await page.goto("/favorites");

  const edit = page.getByRole("button", { name: "编辑标签：收藏 A", exact: true });
  await edit.click();
  await page.getByRole("button", { name: "删除标签：初始", exact: true }).click();
  await edit.click();
  await expect.poll(() => state.patchBodies).toEqual([[]]);

  await edit.click();
  await page.getByRole("button", { name: "添加标签：收藏 A", exact: true }).click();
  const input = page.getByRole("textbox", { name: "添加标签：收藏 A", exact: true });
  await input.fill("最新");
  await input.press("Enter");
  await expect(page.locator(".favorite-card").getByText("最新", { exact: true })).toBeVisible();
  await edit.click();

  releaseFirstPatch();
  await expect.poll(() => state.patchBodies).toEqual([[], ["最新"]]);
  await expect(page.locator(".favorite-card").getByText("最新", { exact: true })).toBeVisible();
  await expect(page.locator(".favorite-card").getByText("未设置标签", { exact: true })).toHaveCount(0);
});

test("leaving list selection preserves detail tag editing and pending changes", async ({ page }) => {
  const state: FavoriteApiState = {
    favorites: [favorite("a", "收藏 A", ["待移除", "保留"]), favorite("b", "收藏 B", [])],
    patchBodies: []
  };
  await mockFavoriteWorkspace(page, state);
  await page.goto("/favorites");
  await page.getByRole("button", { name: "查看收藏：收藏 A", exact: true }).click();
  await page.getByRole("button", { name: "多选收藏", exact: true }).click();
  const detail = page.getByRole("complementary", { name: "收藏详情", exact: true });
  const edit = detail.getByRole("button", { name: "编辑标签：收藏 A", exact: true });
  await edit.click();
  await detail.getByRole("button", { name: "删除标签：待移除", exact: true }).click();
  // Keyboard activation isolates leaving selection from the normal outside-click save.
  await page.getByRole("button", { name: "退出收藏多选", exact: true }).press("Enter");
  await expect(page.getByRole("button", { name: "多选收藏", exact: true })).toBeVisible();
  await expect(detail.getByRole("button", { name: "删除标签：保留", exact: true })).toBeVisible();
  await expect(detail.getByRole("button", { name: "返回原聊天", exact: true })).toBeVisible();
  expect(state.patchBodies).toEqual([]);
  await edit.click();
  await expect.poll(() => state.patchBodies).toEqual([["保留"]]);
});

test("report favorites separate saved metadata from readable content on desktop and mobile", async ({ page }) => {
  const report = {
    ...favorite("report", "其它医疗报告 - dv", []),
    source_type: "report" as const,
    member_id: "member-a",
    member_name: "小安",
    content_summary: "# 其它医疗报告 - dv\n\n- **医疗报告类型**：其它医疗报告\n- **医疗报告时间**：2026-09-06T05:57:00+08:00",
    content_snapshot: "# 其它医疗报告 - dv\n\n- **医疗报告类型**：其它医疗报告\n- **医疗报告时间**：2026-09-06T05:57:00+08:00\n- **就诊机构**：示例医院\n\n## 医疗报告内容\n\n保存的报告正文。"
  };
  await mockFavoriteWorkspace(page, { favorites: [report], patchBodies: [] });
  await page.goto("/favorites");
  const card = page.getByRole("button", { name: "查看收藏：其它医疗报告 - dv", exact: true });
  await expect(card).not.toContainText("**");
  await expect(card).not.toContainText("2026-09-06T");
  await card.click();
  const detail = page.getByRole("complementary", { name: "收藏详情", exact: true });
  const expectedTime=await page.evaluate(()=>{const d=new Date('2026-09-06T05:57:00+08:00');return `${d.getFullYear()}年${d.getMonth()+1}月${d.getDate()}日 ${String(d.getHours()).padStart(2,'0')}:${String(d.getMinutes()).padStart(2,'0')}`;});
  await expect(detail).toContainText(expectedTime);
  await expect(detail).not.toContainText('UTC+08:00');
  await expect(detail).toContainText("保存的报告正文。");
  await expect(detail).not.toContainText("其它医疗报告 - dv");
  await expect(detail.getByRole("button", { name: "查看原医疗报告" })).toBeVisible();
  await expect(detail.getByRole("heading", { name: "医疗报告内容", exact: true })).toBeVisible();
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(detail).toBeVisible();
  await expect(card).not.toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  const bounds = await detail.locator(".favorite-report-fields").boundingBox();
  expect(bounds!.x).toBeGreaterThanOrEqual(0);
  expect(bounds!.x + bounds!.width).toBeLessThanOrEqual(390);
});
