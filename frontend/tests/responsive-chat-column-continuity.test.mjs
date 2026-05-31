import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import assert from "node:assert/strict";

const root = dirname(dirname(fileURLToPath(import.meta.url)));
const styles = readFileSync(join(root, "src/styles/conversations.css"), "utf8");

assert(
  !styles.includes("@media (max-width: 650px) {\n  .home-workspace {\n    gap: 10px;\n    padding: 14px 14px 16px;"),
  "narrow workspace should not keep the old titlebar-adjacent gap"
);

assert(
  styles.includes("@media (max-width: 650px) {\n  .home-workspace {\n    gap: 0;\n    padding: 0;\n  }\n\n  .home-workspace-content {\n    padding: 0;"),
  "narrow workspace should remove body padding consistently with wide and split layouts"
);

assert(
  styles.includes("  .home-workspace-content {\n    --chat-column-side-gap: 18px;\n    --chat-column-width: calc(100cqw - (var(--chat-column-side-gap) * 2));"),
  "narrow conversation column should keep the same side gap formula as split-screen widths"
);

assert(
  !styles.includes("--chat-column-width: calc(100cqw - 20px);"),
  "narrow conversation column should not jump to a different hard-coded width formula"
);
