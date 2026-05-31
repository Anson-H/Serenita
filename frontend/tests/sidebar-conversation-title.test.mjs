import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import assert from "node:assert/strict";

const root = dirname(dirname(fileURLToPath(import.meta.url)));
const styles = readFileSync(join(root, "src/styles/shell.css"), "utf8");
const anchoredTitleRule = styles.match(
  /\/\* Conversation titles stay readable and anchored on the sidebar rail\. \*\/[\s\S]*?\.conversation-title-button \{([\s\S]*?)\n\}/
);

assert(anchoredTitleRule, "sidebar conversation title rule should exist");

assert(
  styles.includes(".patient-sidebar .primary-action,\n.patient-sidebar .nav-item,\n.patient-sidebar .conversation-title-button,\n.patient-sidebar .account-button {\n  font-size: 15px;"),
  "sidebar navigation rows should share the 15px text size"
);
assert(
  styles.includes(".patient-sidebar .account-button strong {\n  font-size: 15px;"),
  "sidebar account name should use the 15px text size"
);
assert(
  styles.includes(".patient-sidebar .nav-item,\n.patient-sidebar .account-button strong {\n  font-weight: 680;"),
  "sidebar labels and account names should keep the quiet label weight"
);
assert(
  styles.includes(".patient-sidebar .conversation-title-button {\n  font-weight: 400;"),
  "sidebar conversation history titles should not be bold"
);
assert(
  styles.includes("justify-content: flex-start;"),
  "conversation title text should align to the left"
);
assert(
  styles.includes("text-align: left;"),
  "conversation title button should not center its text"
);
assert(
  anchoredTitleRule[1].includes("min-height: 40px;"),
  "conversation title buttons should be 40px tall"
);
assert(
  styles.includes(".conversation-delete-button {\n  position: static;"),
  "conversation delete control should not use absolute positioning inside the title row"
);
