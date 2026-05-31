import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import assert from "node:assert/strict";

const root = dirname(dirname(fileURLToPath(import.meta.url)));
const conversations = readFileSync(join(root, "src/styles/conversations.css"), "utf8");
const responsive = readFileSync(join(root, "src/styles/responsive.css"), "utf8");

assert(
  !conversations.includes("@media (max-width: 650px) {\n  .home-workspace {\n    gap: 10px;\n    padding: 14px 14px 16px;"),
  "narrow home workspace should not keep the old extra top padding"
);

assert(
  conversations.includes(".home-workspace {\n  display: flex;\n  flex-direction: column;\n  gap: 0;\n  height: 100%;\n  min-height: 0;\n  overflow: hidden;\n  padding: 0;\n}") &&
    conversations.includes(".home-workspace-content {\n  --composer-overlay-height: 178px;\n  --chat-border-safe-space: 4px;\n  --chat-scrollbar-gutter: 16px;\n  --chat-scrollbar-axis-offset: 0px;\n  --chat-column-side-gap: clamp(18px, calc((100cqw - 840px) / 2), 118px);\n  --chat-column-width: min(840px, calc(100cqw - (var(--chat-column-side-gap) * 2)));\n  container-type: inline-size;\n  position: relative;\n  display: grid;\n  grid-template-rows: minmax(0, 1fr);\n  flex: 1 1 auto;\n  min-width: 0;\n  min-height: 0;\n  overflow: hidden;\n  padding: 0;\n  background: transparent;\n  box-shadow: none;\n}") &&
    conversations.includes("@media (max-width: 650px) {\n  .home-workspace {\n    gap: 0;\n    padding: 0;\n  }\n\n  .home-workspace-content {\n    padding: 0;"),
  "home workspace should keep titlebar spacing separate from body padding"
);

assert(
  conversations.includes(".workspace-titlebar h1 {\n  justify-self: center;"),
  "workspace title should stay centered in the titlebar"
);

assert(
  conversations.includes("  .conversation-surface .empty-state {\n    min-height: min(420px, 58vh);\n    padding: clamp(22px, 5vw, 46px);"),
  "empty state should not get shorter at the narrow breakpoint"
);

assert(
  responsive.includes("  .home-workspace .conversation-surface {\n    min-height: 0;\n    border-radius: inherit;\n    padding: 0;"),
  "conversation surface should not add internal padding at the narrow breakpoint"
);

assert(
  responsive.includes("  .home-workspace-content > form {\n    bottom: 14px;\n    border-radius: var(--radius-panel);\n    padding: 16px 12px 12px;"),
  "composer container should not move upward or lose top padding at the narrow breakpoint"
);
