import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import assert from "node:assert/strict";

const root = dirname(dirname(fileURLToPath(import.meta.url)));
const read = (path) => readFileSync(join(root, path), "utf8");

const composer = read("src/features/conversations/ConversationComposer.tsx");
const layout = read("src/features/conversations/useConversationLayout.ts");
const workspaceTypes = read("src/features/conversations/workspaceTypes.ts");
const styles = read("src/styles/composer.css");

assert(
  !composer.includes("deepseek-composer") && !styles.includes("deepseek-composer"),
  "composer should not use provider-specific deepseek class names"
);
assert(
  composer.includes('className="assistant-composer conversation-composer"'),
  "composer surface should use a provider-neutral class name"
);
assert(composer.includes("rows={1}"), "composer textarea should declare a single initial row");
assert(
  layout.includes("const COMPOSER_TEXTAREA_MIN_HEIGHT_PX = 24;"),
  "composer textarea minimum height should leave room for stable caret rendering"
);
assert(
  styles.includes("height: 24px;\n  min-height: 24px;"),
  "composer textarea CSS should start as a compact line with caret breathing room"
);
assert(
  styles.includes(".conversation-composer textarea {\n  color: var(--ink-strong);\n  line-height: var(--conversation-copy-line-height);"),
  "composer textarea line-height should match its compact height after later style overrides"
);
assert(
  styles.includes(".assistant-composer textarea,\n.conversation-composer textarea {\n  border: 0;\n  border-color: transparent;\n  background: transparent;"),
  "composer textarea should share the composer surface background"
);
assert(
  workspaceTypes.includes('placeholder: "问问Serenita"'),
  "home composer placeholder should invite asking Serenita directly"
);
assert(
  !workspaceTypes.includes("例如：我下周复查"),
  "home composer placeholder should not show a long example sentence"
);
