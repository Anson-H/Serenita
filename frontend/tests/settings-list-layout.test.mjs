import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import assert from "node:assert/strict";

const root = dirname(dirname(fileURLToPath(import.meta.url)));
const styles = readFileSync(join(root, "src/styles/settings.css"), "utf8");
const viewSource = readFileSync(join(root, "src/features/settings/SettingsView.tsx"), "utf8");

assert(
  styles.includes(".settings-workspace .settings-root-list,\n.settings-workspace .provider-list {\n  gap: 5px;"),
  "primary and provider settings lists should use a 5px button row gap"
);

assert(
  styles.includes("--settings-row-height: 40px;"),
  "primary and provider settings buttons should be 40px tall"
);

assert(
  styles.includes(".settings-workspace .settings-nav-item,\n.settings-workspace .provider-row strong {\n  font-size: 15px;"),
  "primary and provider settings buttons should use 15px text"
);

assert(
  styles.includes(".settings-workspace .settings-nav-item > span:first-child {\n  justify-self: start;\n  text-align: left;"),
  "primary settings labels should align left like provider rows"
);

assert(
  viewSource.includes('<span className="settings-nav-chevron provider-row-chevron" aria-hidden="true">'),
  "provider row chevrons should use the same non-interactive visual element as primary settings rows"
);

assert(
  !viewSource.includes('aria-label={`查看模型提供方：${provider.provider_name}`}'),
  "provider row chevrons should not render as separate detail buttons"
);

assert(
  styles.includes(".settings-workspace .settings-sign-out-button > span:first-child {\n  justify-self: center;\n  text-align: center;"),
  "settings sign-out label should be centered within its button"
);

assert(
  styles.includes(".settings-workspace .settings-sign-out-button.danger {\n  grid-template-columns: minmax(0, 1fr);\n  padding: 0 8px;"),
  "settings sign-out button should use symmetric horizontal padding for true button centering"
);

assert(
  styles.includes(".settings-workspace .settings-sign-out-button {\n  margin-top: 0;"),
  "settings sign-out row should not add extra list spacing"
);

assert(
  styles.includes(".settings-workspace .provider-row-actions .provider-configured-icon {\n  width: 18px;"),
  "provider status icons should reserve a full square hitbox"
);

assert(
  styles.includes("  min-height: 18px;\n  padding: 0;\n  overflow: visible;"),
  "provider status icons should not inherit pill padding or clipping"
);

assert(
  !styles.includes("provider-default-icon"),
  "provider list should not reserve space for a meaningless default star"
);

assert(
  styles.includes(".settings-workspace .model-row {\n  display: grid;\n  grid-template-columns: minmax(0, 1fr) var(--settings-icon-button-size);"),
  "added model rows should use a fixed action column aligned with form icon buttons"
);

assert(
  styles.includes("  padding: 0 5px 0 10px;"),
  "added model rows should align delete buttons with the API key visibility button"
);

assert(
  styles.includes(".settings-workspace .model-row-actions {\n  justify-self: end;\n  flex-wrap: nowrap;\n  width: var(--settings-icon-button-size);"),
  "added model row actions should not drift or wrap away from the right edge"
);
