import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import assert from "node:assert/strict";

const root = dirname(dirname(fileURLToPath(import.meta.url)));
const read = (path) => readFileSync(join(root, path), "utf8");

const pageState = read("src/features/conversations/useConversationPageState.ts");
const pageModel = read("src/features/conversations/useWorkspacePageModel.ts");
const lifecycle = read("src/features/conversations/useConversationLifecycle.ts");
const workspace = read("src/features/conversations/useConversationWorkspace.ts");

assert(
  pageState.includes("type HomeConversationDraft = {") &&
    pageState.includes("const homeConversationDraftRef = useRef<HomeConversationDraft | null>(null)") &&
    pageState.includes("homeConversationDraftRef,"),
  "conversation page state should own an in-memory home draft ref"
);

assert(
  pageModel.includes("homeConversationDraftRef,") &&
    pageModel.includes("homeConversationDraftRef,") &&
    pageModel.includes("clearHomeConversationDraft: lifecycle.clearHomeConversationDraft"),
  "workspace page model should pass the home draft ref through lifecycle and clear it after submit"
);

assert(
  lifecycle.includes("function saveHomeConversationDraft") &&
    lifecycle.includes("function restoreHomeConversationDraft") &&
    lifecycle.includes("saveHomeConversationDraft();") &&
    lifecycle.includes("restoreHomeConversationDraft()"),
  "conversation lifecycle should save draft state before leaving home and restore it when starting from another route"
);

const openConversationSource = lifecycle.split("async function openConversation")[1].split(
  "async function openFavoriteSourceConversation",
  1
)[0];

assert(
  openConversationSource.includes("saveHomeConversationDraft();") &&
    openConversationSource.includes("clearActiveComposerDraft();"),
  "opening a history conversation should save the home draft, then clear active composer state"
);

const startConversationSource = lifecycle.split("function startConversation")[1].split(
  "async function deleteConversationFromSidebar",
  1
)[0];

assert(
  startConversationSource.includes("const shouldRestoreDraft") &&
    startConversationSource.includes("saveHomeConversationDraft();") &&
    startConversationSource.includes("restoreHomeConversationDraft()") &&
    startConversationSource.includes("clearHomeConversationDraft();"),
  "starting a conversation away from the current home draft should restore saved draft or clear intentionally"
);

assert(
  workspace.includes("clearHomeConversationDraft: () => void;") &&
    workspace.includes("clearHomeConversationDraft,") &&
    workspace.includes("clearHomeConversationDraft();"),
  "submitting the draft should clear the saved home draft snapshot"
);
