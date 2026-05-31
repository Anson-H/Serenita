import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import assert from "node:assert/strict";

const root = dirname(dirname(fileURLToPath(import.meta.url)));
const read = (path) => readFileSync(join(root, path), "utf8");

const sidebar = read("src/app/Sidebar.tsx");
const settingsView = read("src/features/settings/SettingsView.tsx");

assert(!sidebar.includes("<small>{currentSession.account}</small>"), "sidebar account button must not show account id");
assert(!sidebar.includes("account-menu"), "sidebar account menu popover should be removed");
assert(!sidebar.includes('aria-haspopup="menu"'), "account button should no longer own a menu");
assert(sidebar.includes('aria-label="账号设置"'), "sidebar account summary should open account settings");
assert(sidebar.includes('onClick={() => onNavigate(SETTING_PATH)}'), "clicking the account summary should navigate to settings");
assert(sidebar.includes('route === SETTING_PATH ? "account-button active" : "account-button"'), "account summary should light up as one active control");
assert(!sidebar.includes("account-settings-button"), "settings entry should not be a separate icon button");

assert(settingsView.includes("onSignOut"), "settings view should accept a sign-out handler");
assert(settingsView.includes("退出登录"), "sign out should be available in settings");
assert(settingsView.includes("settings-sign-out-button"), "sign out should be a first-level settings action");
