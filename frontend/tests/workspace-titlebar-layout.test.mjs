import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import assert from "node:assert/strict";

const root = dirname(dirname(fileURLToPath(import.meta.url)));
const read = (path) => readFileSync(join(root, path), "utf8");

const homeWorkspace = read("src/features/conversations/HomeWorkspace.tsx");
const styles = read("src/styles/conversations.css");
const homeWorkspaceBody = homeWorkspace.slice(homeWorkspace.indexOf("export function HomeWorkspace"));

assert(
  homeWorkspaceBody.includes('className="workspace-titlebar"') &&
    homeWorkspaceBody.includes("<h1>{workspaceTitle}</h1>"),
  "home workspace title should render in the top titlebar"
);

assert(
  homeWorkspaceBody.includes('className="home-workspace-header"') &&
    homeWorkspaceBody.includes('className="home-workspace-content"') &&
    homeWorkspaceBody.indexOf('className="home-workspace-header"') <
      homeWorkspaceBody.indexOf('className="workspace-titlebar"') &&
    homeWorkspaceBody.includes('className="home-workspace-content" ref={conversationStageRef}'),
  "home workspace should split the titlebar and conversation body into separate structural containers"
);

assert(
  !homeWorkspaceBody.includes('className="conversation-stage"'),
  "home workspace content should be the single conversation body container"
);

assert(
  !homeWorkspaceBody.includes('className="workspace-header"'),
  "home workspace should not render the old lower title header"
);

assert(
  styles.includes(".home-workspace-header {\n  flex: 0 0 auto;\n  min-width: 0;\n}") &&
    styles.includes(".home-workspace-content {\n  --composer-overlay-height: 178px;\n  --chat-border-safe-space: 4px;\n  --chat-scrollbar-gutter: 16px;\n  --chat-scrollbar-axis-offset: 0px;\n  --chat-column-side-gap: clamp(18px, calc((100cqw - 840px) / 2), 118px);\n  --chat-column-width: min(840px, calc(100cqw - (var(--chat-column-side-gap) * 2)));\n  container-type: inline-size;\n  position: relative;\n  display: grid;\n  grid-template-rows: minmax(0, 1fr);\n  flex: 1 1 auto;\n  min-width: 0;\n  min-height: 0;\n  overflow: hidden;\n  padding: 0;\n  background: transparent;\n  box-shadow: none;\n}"),
  "home workspace should mirror the sidebar header/content split so titlebar spacing and body spacing are independent"
);

assert(
  styles.includes(".workspace-titlebar {\n  display: grid;\n  grid-template-columns: var(--workspace-titlebar-side) minmax(0, 1fr) var(--workspace-titlebar-side);\n  align-items: center;\n  height: var(--workspace-titlebar-height);\n  min-height: var(--workspace-titlebar-height);\n  padding: 0 12px;\n}") &&
    styles.includes(".workspace-titlebar h1 {\n  justify-self: center;"),
  "home workspace titlebar should reserve side columns, match settings titlebar height and padding, and center the title"
);
