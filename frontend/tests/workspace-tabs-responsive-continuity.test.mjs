import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import assert from "node:assert/strict";

const root = dirname(dirname(fileURLToPath(import.meta.url)));
const conversations = readFileSync(join(root, "src/styles/conversations.css"), "utf8");
const responsive = readFileSync(join(root, "src/styles/responsive.css"), "utf8");

assert(
  conversations.includes("@media (max-width: 650px) {\n  .home-workspace {\n    gap: 0;"),
  "home workspace should still have a narrow-screen block"
);

assert(
  !conversations.includes("workspace-tabs"),
  "conversation workspace should no longer own the scene switcher tabs"
);

assert(
  !responsive.includes(".home-workspace .workspace-tab"),
  "responsive styles should not carry obsolete home workspace tab overrides"
);

assert(
  conversations.includes(".workspace-titlebar {\n  display: grid;\n  grid-template-columns: var(--workspace-titlebar-side) minmax(0, 1fr) var(--workspace-titlebar-side);"),
  "home workspace should reserve balanced side columns for the centered title"
);
