import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import assert from "node:assert/strict";

const root = dirname(dirname(fileURLToPath(import.meta.url)));
const source = readFileSync(join(root, "src/features/conversations/thinking.ts"), "utf8");

assert(
  source.includes("思考完成（用时 ${formatThinkingDuration(message.duration_ms)}）"),
  "thinking completion summary should include a space before the formatted duration"
);

assert(
  !source.includes("思考完成（用时${formatThinkingDuration(message.duration_ms)}）"),
  "thinking completion summary should not jam the duration directly after 用时"
);
