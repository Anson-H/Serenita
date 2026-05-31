import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import assert from "node:assert/strict";

const root = dirname(dirname(fileURLToPath(import.meta.url)));
const read = (path) => readFileSync(join(root, path), "utf8");

const sidebar = read("src/app/Sidebar.tsx");
const patientShell = read("src/app/PatientShell.tsx");
const routeShell = read("src/app/WorkspaceRouteShell.tsx");
const routeContent = read("src/features/conversations/WorkspaceRouteContent.tsx");

assert(
  sidebar.includes("currentSessionId: string | null;"),
  "sidebar should accept the current conversation session id"
);
assert(
  sidebar.includes('conversation.session_id === currentSessionId ? "conversation-item-frame active" : "conversation-item-frame"'),
  "sidebar should mark the active conversation row"
);
assert(
  sidebar.includes('className="conversation-title-button"'),
  "active state should not be placed on the title button alone"
);
assert(
  sidebar.includes('aria-current={conversation.session_id === currentSessionId ? "page" : undefined}'),
  "active conversation should expose aria-current"
);
assert(
  patientShell.includes("currentSessionId={currentSessionId}"),
  "patient shell should pass current session id into sidebar"
);
assert(
  routeShell.includes("currentSessionId={currentSessionId}"),
  "route shell should pass current session id into the shell component"
);
assert(
  routeContent.includes("currentSessionId={pageState.currentSessionId}"),
  "workspace content should pass page state current session id into route shell"
);
