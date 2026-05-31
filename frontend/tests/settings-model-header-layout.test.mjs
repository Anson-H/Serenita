import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import assert from "node:assert/strict";

const root = dirname(dirname(fileURLToPath(import.meta.url)));
const viewSource = readFileSync(join(root, "src/features/settings/SettingsView.tsx"), "utf8");
const styles = readFileSync(join(root, "src/styles/settings.css"), "utf8");

const titleIndex = viewSource.indexOf('<div className="model-section-title">');
const countIndex = viewSource.indexOf('<span className="status">{selectedProviderModels.length} 个模型</span>');
const addIndex = viewSource.indexOf('aria-label="添加模型"');
const titleCloseIndex = viewSource.indexOf("</div>", countIndex);

assert(
  titleIndex >= 0 && countIndex > titleIndex && addIndex > countIndex && addIndex < titleCloseIndex,
  "add model button should sit inside the model title group after the count"
);

assert(
  styles.includes(".settings-workspace .model-section-header {\n  justify-content: flex-start;"),
  "model section header should not push the add button to the far right"
);

assert(
  styles.includes(".settings-workspace .model-section-title {\n  flex-wrap: nowrap;"),
  "model title, count, and add button should stay together"
);
