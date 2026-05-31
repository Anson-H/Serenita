import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import assert from "node:assert/strict";

const root = dirname(dirname(fileURLToPath(import.meta.url)));
const styles = readFileSync(join(root, "src/styles/shell.css"), "utf8");

assert(
  styles.includes(".sidebar-scenario-nav {\n  display: grid;\n  grid-template-columns: repeat(2, minmax(0, 1fr));") &&
    styles.includes("  padding-bottom: 10px;") &&
    styles.includes("  border-bottom: 1px solid var(--line);") &&
    styles.includes(".sidebar-scenario-tab {\n  display: flex;") &&
    styles.includes("  border: 1px solid var(--line);") &&
    styles.includes("  background: var(--surface-raised);") &&
    styles.includes("  font-size: 15px;\n  font-weight: 680;"),
  "sidebar scene tabs should be horizontal, separated from the primary action, button-like, and match the left navigation text scale"
);

assert(
  styles.includes(".scenario-icon-frame {") &&
    styles.includes("  width: var(--icon-size);") &&
    !styles.includes(".scenario-icon-frame {\n  display: inline-grid;\n  flex: 0 0 auto;\n  width: 24px;\n  height: 24px;\n  place-items: center;\n  border: 1px solid var(--line);"),
  "sidebar scene tab icons should not have their own visible wrapper border"
);

assert(
  styles.includes(".brand-row {\n  display: flex;") &&
    styles.includes("  height: var(--workspace-titlebar-height);") &&
    styles.includes("  min-height: var(--workspace-titlebar-height);") &&
    styles.includes("  padding: 0 12px;"),
  "sidebar brand row should match the account settings titlebar height and padding"
);

assert(
    styles.includes(".patient-sidebar {\n  border-right-color: oklch(84% 0.028 278);\n  background:\n    linear-gradient(180deg, oklch(99% 0.006 286 / 0.96), oklch(96.8% 0.018 284 / 0.96));\n  padding: 0;\n  gap: 0;\n}") &&
    styles.includes(".sidebar-content {\n  display: flex;\n  flex: 1 1 auto;\n  flex-direction: column;\n  gap: 18px;\n  min-width: 0;\n  min-height: 0;\n  padding: 0 18px 20px;\n}"),
  "sidebar should keep header/content flush while spacing lower content sections"
);
