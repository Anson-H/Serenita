import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import assert from "node:assert/strict";

const root = dirname(dirname(fileURLToPath(import.meta.url)));
const component = readFileSync(join(root, "src/features/favorites/FavoritesWorkspace.tsx"), "utf8");
const styles = readFileSync(join(root, "src/styles/favorites.css"), "utf8");

assert(
  component.includes('className="favorites-workspace-header"') &&
    component.includes('className="favorites-workspace-content"') &&
    component.indexOf('className="favorites-workspace-header"') <
      component.indexOf("{favoriteToolbar}") &&
    component.indexOf('className="favorites-workspace-content"') <
      component.indexOf('className="favorite-layout"'),
  "favorites workspace should split its titlebar and content into separate structural containers"
);

assert(
  !styles.includes("height: 58px") &&
    !styles.includes("min-height: 58px"),
  "favorites toolbar should not override the shared titlebar height"
);

assert(
  styles.includes(".favorites-workspace .favorite-toolbar {\n  height: var(--workspace-titlebar-height);\n  min-height: var(--workspace-titlebar-height);\n  border-bottom-color: transparent;\n  padding: 0 12px;\n}"),
  "favorites toolbar should match the shared 52px titlebar height and padding"
);

assert(
  styles.includes(".favorites-workspace-header {\n  flex: 0 0 auto;\n  min-width: 0;\n}") &&
    styles.includes(".favorites-workspace-content {\n  display: grid;\n  grid-template-rows: minmax(0, 1fr);\n  flex: 1 1 auto;\n  min-width: 0;\n  min-height: 0;\n  padding: 0 22px 20px;\n}"),
  "favorites workspace should mirror the shared header/content shell structure"
);
