import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import assert from "node:assert/strict";

const root = dirname(dirname(fileURLToPath(import.meta.url)));
const read = (path) => readFileSync(join(root, path), "utf8");

const homeWorkspace = read("src/features/conversations/HomeWorkspace.tsx");
const conversations = read("src/styles/conversations.css");
const composer = read("src/styles/composer.css");
const frontendReadme = read("README.md");
const sharedDesign = read("../docs/shared/frontend-design.md");

assert(
  homeWorkspace.includes('data-home-empty={messagesLength ? undefined : "true"}'),
  "home workspace should expose the empty-home layout state to CSS"
);

assert(
  homeWorkspace.includes('className="home-empty-center"') &&
    homeWorkspace.includes("messagesLength ? composer : null"),
  "empty home should place the prompt and composer in the same centered layout group"
);

assert(
  conversations.includes(".home-empty-center {\n  align-self: center;\n  justify-self: center;") &&
    conversations.includes('.home-workspace[data-home-empty="true"] .conversation-surface {\n  align-content: center;') &&
    conversations.includes(".home-empty-center .empty-state {\n  width: 100%;\n  justify-items: center;\n  text-align: center;"),
  "empty home prompt should be centered inside the shared empty-home group"
);

assert(
  conversations.includes("  gap: 20px;\n  padding: 0;") &&
    conversations.includes(".home-workspace[data-home-empty=\"true\"] .home-empty-center .empty-state {") &&
    conversations.includes("  max-width: none;\n  min-height: auto;\n  padding: 0;\n}") &&
    conversations.includes(".conversation-surface .empty-state strong {\n  max-width: 18ch;\n  font-size: var(--text-brand);"),
  "empty home prompt spacing and font size should stay fixed across responsive layouts"
);

assert(
  !conversations.includes("font-size: clamp(22px, 3vw, 34px);") &&
    !conversations.includes("  .conversation-surface .empty-state strong {\n    font-size: 24px;\n  }") &&
    !conversations.includes("gap: clamp(24px, 4vh, 40px);"),
  "empty home should not use viewport-dependent prompt typography or prompt-composer spacing"
);

assert(
  composer.includes(".home-empty-center .conversation-composer {\n  position: relative;\n  left: auto;\n  right: auto;\n  bottom: auto;\n  width: 100%;\n  transform: none;"),
  "empty home composer should be centered in normal document flow rather than pinned to the bottom"
);

assert(
  frontendReadme.includes("空首页时，提示文案和输入区组成同一个居中组") &&
    sharedDesign.includes("空首页的提示文案和输入框必须作为一个整体在首页内容区居中"),
  "frontend docs should describe the centered empty-home prompt and input"
);
