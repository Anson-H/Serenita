import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import assert from "node:assert/strict";

const root = dirname(dirname(fileURLToPath(import.meta.url)));
const settings = readFileSync(join(root, "src/styles/settings.css"), "utf8");
const base = readFileSync(join(root, "src/styles/base.css"), "utf8");
const viewSource = readFileSync(join(root, "src/features/settings/SettingsView.tsx"), "utf8");

assert(
  !viewSource.includes("provider-detail-header"),
  "provider detail pane should not render the removed top header container"
);

assert(
  !viewSource.includes("provider-test-button"),
  "provider detail pane should not render a second connection-test button"
);

assert(
  settings.includes(".settings-workspace .settings-section > h1 {\n  display: none;"),
  "settings detail panes should not show a second title"
);

assert(
  settings.includes(".settings-workspace .password-section .command-button {\n  justify-self: stretch;\n  width: min(100%, 1040px);"),
  "password submit button should align to the password fields"
);

assert(
  base.includes("min-width: 300px;"),
  "global minimum viewport width should be 300px"
);
