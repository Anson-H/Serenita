import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import assert from "node:assert/strict";

const root = dirname(dirname(fileURLToPath(import.meta.url)));
const tokens = readFileSync(join(root, "src/styles/tokens.css"), "utf8");
const conversations = readFileSync(join(root, "src/styles/conversations.css"), "utf8");

assert(
  tokens.includes("--text-ui: 15px;"),
  "root UI text size should be 15px"
);

assert(
  conversations.includes(".thinking-duration {\n  color: var(--accent-strong);\n  font-size: inherit;"),
  "thinking completion summary should inherit the 15px root UI size"
);

assert(
  conversations.includes(".thinking-process .markdown-content {\n  margin-top: 6px;\n  font-size: 0.92em;"),
  "expanded thinking process content should use a relative compact text size"
);

assert(
  conversations.includes(".thinking-process {\n  border: 0;\n  background: oklch(96.2% 0.014 284 / 0.72);\n  box-shadow: none;\n  font-size: inherit;\n  line-height: var(--conversation-copy-line-height);\n  padding: 8px 2px 8px;"),
  "thinking process text should align with assistant reply text"
);
