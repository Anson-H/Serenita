import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import assert from "node:assert/strict";

const root = dirname(dirname(fileURLToPath(import.meta.url)));
const sidebar = readFileSync(join(root, "src/app/Sidebar.tsx"), "utf8");
const styles = `${readFileSync(join(root, "src/styles/shell.css"), "utf8")}\n${readFileSync(
  join(root, "src/styles/conversations.css"),
  "utf8"
)}`;

assert(
  styles.includes("--sidebar-scrollbar-gutter: 19px;"),
  "sidebar should define the gap from controls to the sidebar rail"
);
assert(
  styles.includes("margin-right: calc(var(--sidebar-scrollbar-gutter) * -1);"),
  "conversation list should let its scrollbar sit on the sidebar edge"
);
assert.match(
  styles,
  /\/\* Sidebar history final layout override[\s\S]*?\.conversation-list \{\n  align-content: start;\n  flex: 1 1 auto;\n  gap: 5px;\n  grid-auto-rows: max-content;\n\}/,
  "conversation list should use 5px spacing, fill the sidebar history area, and keep history rows top-aligned"
);
assert(
  styles.includes("width: calc(100% - var(--sidebar-scrollbar-gutter));"),
  "conversation rows should keep delete controls aligned with fixed sidebar controls"
);
assert(
  styles.includes(".conversation-item-row {\n  display: block;\n  width: calc(100% - var(--sidebar-scrollbar-gutter));"),
  "conversation rows should not keep the old grid gap"
);
assert(
  styles.includes(".conversation-item-frame {\n  width: 100%;"),
  "conversation item frame should fill the aligned row"
);
assert(
  styles.includes("justify-self: end;"),
  "conversation delete button should sit on the right edge of the row"
);
assert(
  styles.includes("margin-right: 6px;"),
  "conversation delete button should sit slightly left of the sidebar rail"
);
assert(
  styles.includes(".conversation-item-frame:hover,\n.conversation-item-frame:focus-within,\n.conversation-item-frame.active,\n.conversation-item-frame:has(.conversation-delete-button:hover)"),
  "hovering either conversation title or delete, and the active conversation, should light the outer conversation frame"
);
assert(
  !styles.includes(".conversation-item-frame:has(.conversation-delete-button:hover) .conversation-title-button"),
  "delete button hover should not light the title area separately"
);
assert(
  styles.includes(".conversation-title-button:hover,\n.conversation-title-button:focus-visible {\n  border-color: transparent;\n  background: transparent;"),
  "conversation title hover should not create its own inner highlight"
);
assert(
  styles.includes("button.conversation-delete-button:hover:not(:disabled) {\n  background: transparent;"),
  "delete button hover should not look like a separate highlighted control"
);
assert(
  styles.includes("padding: 0;"),
  "sidebar groups should stay invisible with zero padding"
);
assert(
  styles.includes(".sidebar-bottom::before {"),
  "secondary navigation should be separated from conversation history by a divider"
);
assert(
  styles.includes("border-top: 1px solid var(--line);"),
  "sidebar divider should use the standard hairline color"
);
assert(
  styles.includes(".sidebar-bottom .secondary-nav {\n  gap: 5px;"),
  "health record and favorites entries should use 5px row gap"
);
assert(
  sidebar.includes('<span className="message-meta conversation-list-empty">暂无历史会话</span>'),
  "empty conversation copy should have a dedicated class for list-centered layout"
);
assert(
  styles.includes(".conversation-list {\n  align-content: start;\n  flex: 1 1 auto;\n  gap: 5px;\n  grid-auto-rows: max-content;"),
  "conversation list should fill the sidebar space between primary and secondary nav without stretching history rows"
);
assert(
  styles.includes(".conversation-list-empty {\n  align-self: stretch;") &&
    styles.includes("  display: grid;") &&
    styles.includes("  place-items: center;") &&
    styles.includes("  width: calc(100% - var(--sidebar-scrollbar-gutter));") &&
    styles.includes("  text-align: center;"),
  "empty conversation copy should be centered within the visible list area"
);
