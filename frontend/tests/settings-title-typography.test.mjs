import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import assert from "node:assert/strict";

const root = dirname(dirname(fileURLToPath(import.meta.url)));
const component = readFileSync(join(root, "src/features/settings/SettingsWorkspacePanel.tsx"), "utf8");
const styles = readFileSync(join(root, "src/styles/settings.css"), "utf8");

assert(
  component.includes('className="settings-workspace-header"') &&
    component.includes('className="settings-workspace-content"') &&
    component.indexOf('className="settings-workspace-header"') <
      component.indexOf('className="settings-toolbar"') &&
    component.indexOf('className="settings-workspace-content"') <
      component.indexOf("<SettingsShell"),
  "settings workspace should split its titlebar and content into separate structural containers"
);

assert(
  styles.includes(".settings-workspace .settings-toolbar-title,\n.settings-workspace .settings-mobile-layer-header strong,\n.settings-workspace .settings-section h1 {\n  font-size: 18px;"),
  "settings title surfaces should use 18px text"
);

assert(
  !styles.includes("height: 58px") &&
    !styles.includes("min-height: 58px"),
  "settings toolbar should not override the shared titlebar height"
);

assert(
  styles.includes(".settings-workspace .settings-toolbar {\n  height: var(--workspace-titlebar-height);\n  min-height: var(--workspace-titlebar-height);\n  border-bottom-color: transparent;\n  padding: 0 12px;\n}"),
  "desktop settings toolbar should match the shared 52px titlebar height and padding"
);

assert(
  styles.includes(".settings-workspace .settings-section > h1 {\n  display: none;"),
  "settings detail panes should not show a second title"
);

assert(
  styles.includes(".settings-workspace-header {\n  flex: 0 0 auto;\n  min-width: 0;\n}") &&
    styles.includes(".settings-workspace-content {\n  display: grid;\n  grid-template-rows: minmax(0, 1fr);\n  flex: 1 1 auto;\n  min-width: 0;\n  min-height: 0;\n}"),
  "settings workspace should mirror the shared header/content shell structure"
);
