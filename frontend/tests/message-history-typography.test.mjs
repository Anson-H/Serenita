import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import assert from "node:assert/strict";

const root = dirname(dirname(fileURLToPath(import.meta.url)));
const styles = readFileSync(join(root, "src/styles/conversations.css"), "utf8");

assert(
  styles.includes(".message-entry.user .message-bubble {\n  max-width: min(78%, 660px);\n  border-color: transparent;\n  border-radius: 18px 18px 6px 18px;\n  background: linear-gradient(180deg, oklch(49% 0.125 276), oklch(40% 0.11 276));\n  color: oklch(98.8% 0.006 286);\n  font-size: 15px;"),
  "user questions in message history should use 15px text"
);

assert(
  styles.includes(".message-entry.assistant .markdown-content {\n  color: var(--ink);\n  font-size: 15px;"),
  "assistant replies in message history should keep 15px text"
);
