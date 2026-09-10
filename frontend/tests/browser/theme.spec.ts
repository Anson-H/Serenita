import { expect, test, type Page } from "@playwright/test";
import { mockWorkspace } from "../helpers/workspace";

const palettes = { apricot: "暖杏", sage: "鼠尾草", blue: "雾蓝", mauve: "藕紫", oat: "燕麦" };
async function openThemes(page: Page) {
  await page.goto("/setting");
  await page.getByRole("button", { name: "主题", exact: true }).click();
  await expect(page.getByRole("group", { name: "色彩风格", exact: true })).toBeVisible();
}
async function mode(page: Page, label: string) {
  await page.getByRole("button", { name: "明暗主题", exact: true }).click();
  await page.getByRole("option", { name: label, exact: true }).click();
}

for (const theme of ["light", "dark"] as const) {
  test(`${theme}: every style has readable text, controls, focus and accurate previews`, async ({ page }, info) => {
    await mockWorkspace(page);
    await openThemes(page);
    await expect(page.locator('[aria-labelledby="settings-nav-显示"] button')).toHaveText(["主题", "健康档案", "聊天设置"]);
    await mode(page, theme === "light" ? "浅色" : "深色");
    for (const [style, label] of Object.entries(palettes)) {
      await page.getByRole("button", { name: label, exact: true }).click();
      await expect(page.locator("html")).toHaveAttribute("data-color-style", style);
      await expect(page.locator("html")).toHaveAttribute("data-theme", theme);
      await expect(page.locator('.theme-style-option[aria-pressed="true"]')).toHaveCount(1);
      const result = await page.evaluate(({ style, theme }) => {
        const root = getComputedStyle(document.documentElement);
        const preview = getComputedStyle(document.querySelector(`[data-theme-preview][data-color-style="${style}"]`)!);
        const ctx = document.createElement("canvas").getContext("2d", { willReadFrequently: true })!;
        function rgb(value: string) {
          ctx.clearRect(0, 0, 1, 1); ctx.fillStyle = value; ctx.fillRect(0, 0, 1, 1);
          return Array.from(ctx.getImageData(0, 0, 1, 1).data).slice(0, 3);
        }
        function luminance(value: string) {
          return rgb(value).map(v => v / 255).map(v => v <= .04045 ? v / 12.92 : ((v + .055) / 1.055) ** 2.4)
            .reduce((sum, v, i) => sum + v * [.2126, .7152, .0722][i], 0);
        }
        const color = (name: string) => root.getPropertyValue(`--color-${name}`).trim();
        const contrast = (a: string, b: string) => {
          const aa = luminance(a), bb = luminance(b);
          return (Math.max(aa, bb) + .05) / (Math.min(aa, bb) + .05);
        };
        const backgrounds = ["surface", "rail", "header-surface", "control-surface", "content-inset", "surface-raised", "surface-error", "primary-surface", "primary-hover", "item-hover", "item-current", "danger-soft", "danger-hover", "warning-soft"];
        const failures: string[] = [];
        for (const bg of backgrounds) {
          for (const fg of ["foreground", "foreground-muted"]) {
            const ratio = contrast(color(fg), color(bg));
            if (ratio < 4.5) failures.push(`${fg} on ${bg}: ${ratio.toFixed(2)}`);
          }
          if (preview.getPropertyValue(`--color-${bg}`).trim() !== color(bg)) failures.push(`preview mismatch: ${bg}`);
        }
        for (const bg of ["surface", "control-surface", "header-surface", "item-current", "primary-hover"]) {
          const ratio = contrast(color("accent"), color(bg));
          if (ratio < 3) failures.push(`focus on ${bg}: ${ratio.toFixed(2)}`);
        }
        for (const [fg, bg] of [["danger", "danger-soft"], ["danger", "danger-hover"], ["warning", "warning-soft"], ["success", "surface"]]) {
          const ratio = contrast(color(fg), color(bg));
          if (ratio < 3) failures.push(`semantic icon ${fg} on ${bg}: ${ratio.toFixed(2)}`);
        }
        const expected = theme === "light" ? 0 : 255;
        if (rgb(color("foreground")).some(v => v !== expected)) failures.push("primary text is not pure black/white");
        const allowedText = [rgb(color("foreground")).join(","), rgb(color("foreground-muted")).join(",")];
        for (const element of document.querySelectorAll("button, input, textarea, p, h1, h2, h3, .theme-style-description, .theme-preview-description")) {
          if (!element.getClientRects().length) continue;
          const rendered = getComputedStyle(element).color;
          if (!allowedText.includes(rgb(rendered).join(","))) failures.push(`unexpected text color: ${element.className}`);
        }
        return { failures, background: color("surface") };
      }, { style, theme });
      expect(result.failures, `${theme}/${style}`).toEqual([]);
      await page.screenshot({ path: info.outputPath(`${style}-${theme}.png`) });
    }
  });
}

test("system preference, explicit override, reload and other tabs stay synchronized", async ({ page, context }) => {
  await page.emulateMedia({ colorScheme: "light" });
  await mockWorkspace(page); await openThemes(page);
  await page.getByRole("button", { name: "雾蓝", exact: true }).click();
  await page.emulateMedia({ colorScheme: "dark" });
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await expect(page.locator("html")).toHaveAttribute("data-color-style", "blue");
  await mode(page, "浅色");
  await page.emulateMedia({ colorScheme: "light" }); await page.emulateMedia({ colorScheme: "dark" });
  await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
  await page.reload(); await page.getByRole("button", { name: "主题", exact: true }).click();
  await expect(page.getByRole("button", { name: "明暗主题", exact: true })).toHaveText("浅色");
  await expect(page.getByRole("button", { name: "雾蓝", exact: true })).toHaveAttribute("aria-pressed", "true");
  const other = await context.newPage(); await mockWorkspace(other); await openThemes(other);
  await mode(other, "深色");
  await other.getByRole("button", { name: "鼠尾草", exact: true }).click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await expect(page.getByRole("button", { name: "鼠尾草", exact: true })).toHaveAttribute("aria-pressed", "true");
  await mode(page, "跟随系统");
  await page.emulateMedia({ colorScheme: "light" });
  await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
  await other.close();
});

for (const theme of ["light", "dark"] as const) {
  test(`${theme}: login and report creation inherit the saved theme and text colors`, async ({ page }, info) => {
    await page.addInitScript(theme => localStorage.setItem("serenita.appearance", JSON.stringify({ mode: theme, style: "sage" })), theme);
    const apiRequests = (url: URL) => url.pathname.startsWith("/api/");
    await page.route(apiRequests, route => route.fulfill({ json: { authenticated: false } }));
    await page.goto("/");
    await expect(page.locator(".login-form")).toBeVisible();
    const text = await page.locator("html").evaluate(el => getComputedStyle(el).color);
    await expect(page.locator(".login-form input").first()).toHaveCSS("color", text);
    await expect(page.locator(".login-form button[type=submit]")).toHaveCSS("color", text);
    await page.screenshot({ path: info.outputPath(`login-${theme}.png`) });
    await page.unroute(apiRequests);
    await mockWorkspace(page); await page.goto("/reports");
    await page.getByRole("button", { name: "创建医疗报告", exact: true }).click();
    await page.getByRole("button", { name: /^文字录入/ }).click();
    await page.getByRole("button", { name: /^检查报告/ }).click();
    const dialog = page.getByRole("dialog");
    await expect(dialog).toBeVisible();
    await expect(dialog.locator("input").first()).toHaveCSS("color", text);
    const input = dialog.locator("input").first();
    const background = await input.evaluate(el => getComputedStyle(el.closest(".field-row") ?? el).backgroundColor);
    await input.focus();
    await expect.poll(() => input.evaluate(el => getComputedStyle(el.closest(".field-row") ?? el).backgroundColor)).not.toBe(background);
    await page.screenshot({ path: info.outputPath(`report-form-${theme}.png`) });
    await page.getByRole("button", { name: "关闭创建医疗报告", exact: true }).click();
  });
}

test("saved appearance applies before React loads, including the native color scheme", async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem("serenita.appearance", JSON.stringify({ mode: "dark", style: "mauve" })));
  await page.route("**/src/main.tsx*", route => route.abort());
  await page.goto("/");
  await expect(page.locator("#root")).toBeEmpty();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await expect(page.locator("html")).toHaveAttribute("data-color-style", "mauve");
  await expect(page.locator("html")).toHaveCSS("color-scheme", "dark");
});

test("invalid or unavailable storage still permits changing appearance", async ({ page }) => {
  await page.addInitScript(() => {
    localStorage.setItem("serenita.appearance", "null");
    Object.defineProperty(Storage.prototype, "setItem", { value() { throw new DOMException("blocked", "SecurityError"); } });
  });
  await mockWorkspace(page); await openThemes(page); await mode(page, "深色");
  await page.getByRole("button", { name: "燕麦", exact: true }).click();
  await expect(page.locator("html")).toHaveAttribute("data-color-style", "oat");
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
});

test("narrow theme settings support keyboard selection, scrolling and return navigation", async ({ page }, info) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await mockWorkspace(page); await openThemes(page); await mode(page, "深色");
  const oat = page.getByRole("button", { name: "燕麦", exact: true });
  await oat.focus(); await page.keyboard.press("Space");
  await expect(oat).toHaveAttribute("aria-pressed", "true");
  await expect(oat).toHaveAttribute("data-keyboard-focus");
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({ path: info.outputPath("theme-narrow-dark.png") });
  await page.locator(".settings-detail-panel-back-button").click();
  await expect(page.getByRole("button", { name: "主题", exact: true })).toBeFocused();
});
