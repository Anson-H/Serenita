import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import assert from "node:assert/strict";

const root = dirname(dirname(fileURLToPath(import.meta.url)));
const bubbleSource = readFileSync(join(root, "src/features/conversations/ConversationMessageBubble.tsx"), "utf8");
const styles = readFileSync(join(root, "src/styles/conversations.css"), "utf8");

const copyIndex = bubbleSource.indexOf('aria-label="复制消息"');
const regenerateIndex = bubbleSource.indexOf('aria-label="重新生成"');
const branchCreateIndex = bubbleSource.indexOf('aria-label={branchingFromThisMessage ? "已选择分支起点" : "创建分支"}');
const favoriteIndex = bubbleSource.indexOf('aria-label={favorited ? "取消收藏回答" : "收藏回答"}');
const branchControlsIndex = bubbleSource.indexOf("{branchControls}");

assert(
  copyIndex >= 0 && regenerateIndex > copyIndex && branchCreateIndex > regenerateIndex && favoriteIndex > branchCreateIndex,
  "assistant action buttons should be ordered copy, regenerate, branch, favorite"
);

assert(
  branchControlsIndex > favoriteIndex,
  "branch switch control should render after the main assistant action buttons"
);

assert(
  styles.includes(".message-entry.assistant .message-actions {\n  display: flex;\n  flex-wrap: nowrap;\n  justify-content: flex-start;"),
  "assistant message actions should stay on one row"
);

assert(
  styles.includes(".message-entry.assistant .branch-controls {\n  display: inline-flex;\n  flex: 0 0 auto;\n  min-height: 30px;"),
  "branch switch control should stay compact inside the assistant action row"
);
