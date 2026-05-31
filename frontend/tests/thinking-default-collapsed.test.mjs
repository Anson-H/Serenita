import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import assert from "node:assert/strict";

const root = dirname(dirname(fileURLToPath(import.meta.url)));
const source = readFileSync(join(root, "src/features/conversations/ConversationMessageBubble.tsx"), "utf8");

assert(
  !source.includes("\n        open\n"),
  "thinking process details should be collapsed by default"
);
assert(
  source.includes('className="thinking-process"'),
  "thinking process should still render as a details block"
);
