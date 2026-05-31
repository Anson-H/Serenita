import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import assert from "node:assert/strict";

const root = dirname(dirname(fileURLToPath(import.meta.url)));
const shellSource = readFileSync(join(root, "src/features/settings/SettingsShell.tsx"), "utf8");
const viewSource = readFileSync(join(root, "src/features/settings/SettingsView.tsx"), "utf8");
const settingsCopy = `${shellSource}\n${viewSource}`;

assert(
  !settingsCopy.includes("<span>模型服务</span>"),
  "settings navigation should use model provider wording"
);

assert(
  settingsCopy.includes("模型提供方"),
  "settings UI should use model provider wording"
);

assert(
  settingsCopy.includes("模型提供方加载失败"),
  "provider load error should match account settings acceptance wording"
);

assert(
  !settingsCopy.includes("默认模型服务"),
  "provider list should not show a meaningless default provider badge"
);

assert(
  settingsCopy.includes("暂无模型提供方。"),
  "empty provider list should use model provider wording"
);
