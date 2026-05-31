import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import assert from "node:assert/strict";

const root = dirname(dirname(fileURLToPath(import.meta.url)));
const styles = readFileSync(join(root, "src/styles/conversations.css"), "utf8");

assert(
  !styles.includes(".conversation-stage"),
  "conversation body should not keep an extra conversation-stage wrapper"
);

assert(
  styles.includes("  padding: 0;\n  background: transparent;\n  box-shadow: none;\n}"),
  "conversation body container should not tint the workspace background or add outer padding"
);
assert(
  styles.includes(".conversation-surface {\n  border: 0;\n  background: transparent;\n  padding: 0;"),
  "conversation scroll surface should remain transparent without internal padding"
);

assert(
  styles.includes(".conversation-surface .empty-state {\n  align-self: center;\n  align-content: center;\n  min-height: min(420px, 58vh);\n  border: 0;\n  border-radius: 0;\n  background: transparent;\n  padding: clamp(22px, 5vw, 46px);\n  box-shadow: none;\n}"),
  "conversation empty state should not render as a framed card"
);
