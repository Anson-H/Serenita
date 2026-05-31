import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import assert from "node:assert/strict";

const root = dirname(dirname(fileURLToPath(import.meta.url)));
const styles = readFileSync(join(root, "src/styles/composer.css"), "utf8");
const component = readFileSync(
  join(root, "src/features/conversations/ComposerModelControl.tsx"),
  "utf8"
);

assert(
  component.includes('className="composer-model-popover-sections"') &&
    component.includes('className="composer-picker-section composer-thinking-section"') &&
    component.includes('className="composer-picker-divider"') &&
    component.includes('className="composer-picker-section composer-model-section"'),
  "model picker should render thinking and model containers separated by one divider"
);

assert(
  !component.includes('className="composer-model-row"') &&
    !component.includes('modelPickerPanel === "models"') &&
    !component.includes('onSetModelPickerPanel("models")'),
  "model picker should not require a separate row control before showing the model list"
);

assert(
  styles.includes(".composer-model-side-panel {\n  height: 128px;") &&
    styles.includes("  max-height: 128px;") &&
    styles.includes("  overflow: auto;"),
  "model list should show about three models before scrolling"
);

assert(
  !styles.includes("deepseek-composer"),
  "composer styles should not use provider-specific deepseek class names"
);

assert(
  styles.includes(".conversation-composer .composer-model-popover {\n  position: fixed;") &&
    styles.includes("  left: 14px;\n  right: 14px;") &&
    styles.includes("  max-height: min(430px, calc(100dvh - 164px));") &&
    styles.includes("  overflow: hidden;"),
  "model picker should use the same fixed-height sheet across narrow, split, and wide layouts"
);

assert(
  styles.includes(".conversation-composer .composer-model-flyout {\n  position: static;") &&
    styles.includes("  width: 100%;") &&
    styles.includes("  max-height: 128px;") &&
    styles.includes("  overflow: auto;"),
  "model list should be embedded in the sheet and scroll independently on every layout"
);

assert(
  styles.includes(".conversation-composer .composer-model-side-panel {\n  background: transparent;") &&
    styles.includes(".conversation-composer .composer-model-flyout {\n  border: 0;\n  border-radius: 0;\n  background: transparent;\n  box-shadow: none;"),
  "model list container should match the thinking section without its own framed panel"
);
