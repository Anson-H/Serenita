import { expect, test, type Page } from "@playwright/test";

type MockSession = {
  authenticated: boolean;
  accountId: string;
  account: string;
  accountName: string;
};

async function mockAuthenticatedWorkspace(page: Page, session: MockSession) {
  await page.route(url => url.pathname.startsWith("/api/"), async route => {
    const path = new URL(route.request().url()).pathname.slice(4);
    const json = (value: unknown, status = 200) => route.fulfill({ json: value, status });
    if (path === "/conversations/attachment-capabilities") return json({ model_id: new URL(route.request().url()).searchParams.get("model_id"), file_mime_types: ["image/jpeg", "image/png", "application/pdf"] });
    if (path === "/auth/session") {
      return json(session.authenticated
        ? {
            authenticated: true,
            account_id: session.accountId,
            account: session.account,
            account_name: session.accountName,
            expires_at: "2099-01-01T00:00:00+08:00"
          }
        : { authenticated: false });
    }
    if (path === "/force-401") {
      return json({ detail: { code: "SESSION_EXPIRED", message: "登录态已过期。" } }, 401);
    }
    if (path === "/members/access-events") {
      return route.fulfill({ body: "retry: 60000\n\n", contentType: "text/event-stream" });
    }
    if (path === "/members") {
      return json({
        access_revision: 1,
        default_member_id: null,
        initial_member_id: null,
        last_member_id: null,
        members: [],
        startup_mode: "last_used"
      });
    }
    if (path === "/conversations") return json({ sessions: [], has_more: false, next_cursor: null });
    if (path === "/favorites") return json({ favorites: [], has_more: false, next_cursor: null });
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
    return json({ detail: { message: `未模拟 ${path}` } }, 404);
  });
}

test("profile changes synchronize across tabs and a 401 unmounts both workspaces", async ({ page, context }) => {
  const session: MockSession = {
    authenticated: true,
    account: "account-a",
    accountId: "account-a-id",
    accountName: "账号 A"
  };
  await mockAuthenticatedWorkspace(page, session);
  const otherPage = await context.newPage();
  await mockAuthenticatedWorkspace(otherPage, session);

  await Promise.all([page.goto("/"), otherPage.goto("/")]);
  await expect(page.getByRole("button", { name: "账号设置：账号 A", exact: true })).toBeVisible();
  await expect(otherPage.getByRole("button", { name: "账号设置：账号 A", exact: true })).toBeVisible();

  session.account = "account-b";
  session.accountName = "账号 B";
  await page.evaluate(async () => {
    const { publishAuthSessionChange } = await import("../../src/api/authSessionEvents");
    publishAuthSessionChange("refresh");
  });
  await expect(page.getByRole("button", { name: "账号设置：账号 B", exact: true })).toBeVisible();
  await expect(otherPage.getByRole("button", { name: "账号设置：账号 B", exact: true })).toBeVisible();

  session.authenticated = false;
  await page.evaluate(async () => {
    const { request } = await import("../../src/api/request");
    await request("/force-401").catch(() => undefined);
  });
  await expect(page).toHaveURL(/\/sign_in$/);
  await expect(otherPage).toHaveURL(/\/sign_in$/);
  await expect(page.getByRole("textbox", { name: "用户标识", exact: true })).toBeVisible();
  await expect(otherPage.getByRole("textbox", { name: "用户标识", exact: true })).toBeVisible();
});


test("focus refresh overlapping initial authentication settles loading and rejects the late initial session", async ({ page }) => {
  const session: MockSession = { authenticated: true, account: "latest", accountId: "latest-id", accountName: "当前账号" };
  await mockAuthenticatedWorkspace(page, session);
  let release!: () => void;
  const gate = new Promise<void>(resolve => { release = resolve; });
  let requests = 0;
  let refreshing = false;
  await page.route("**/api/auth/session", async route => {
    if (refreshing) return route.fallback();
    requests++;
    await gate;
    return route.fulfill({ json: { authenticated: false } });
  });
  await page.goto("/");
  await expect.poll(() => requests).toBeGreaterThan(0);
  refreshing = true;
  await page.evaluate(() => window.dispatchEvent(new Event("focus")));
  const account = page.getByRole("button", { name: "账号设置：当前账号", exact: true });
  await expect(account).toBeVisible();
  const completed = page.waitForResponse(response => response.url().endsWith("/api/auth/session"));
  release(); await (await completed).finished();
  await page.evaluate(() => new Promise<void>(resolve => requestAnimationFrame(() => requestAnimationFrame(() => resolve()))));
  await expect(account).toBeVisible();
});
