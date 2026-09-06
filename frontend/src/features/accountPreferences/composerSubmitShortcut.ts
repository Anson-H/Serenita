import type { ComposerSubmitShortcut as ApiComposerSubmitShortcut } from "../../api/client";
import {
  readConversationPreferences,
  useConversationPreferences,
  writeConversationPreferences
} from "./conversationPreferences";

export type ComposerSubmitShortcut = ApiComposerSubmitShortcut;

export const composerSubmitShortcutOptions: Array<{
  label: string;
  triggerLabel: string;
  value: ComposerSubmitShortcut;
}> = [
    { label: "按 Enter 发送", triggerLabel: "Enter", value: "enter" },
    {
      label: "按 ⌘/Ctrl + Enter 发送",
      triggerLabel: "⌘/Ctrl + Enter",
      value: "modifier_enter"
    }
  ];

const defaultComposerSubmitShortcut: ComposerSubmitShortcut = "enter";
const availableComposerSubmitShortcuts = new Set<ComposerSubmitShortcut>(
  composerSubmitShortcutOptions.map((option) => option.value)
);
function normalizeComposerSubmitShortcut(value: unknown): ComposerSubmitShortcut {
  return typeof value === "string" &&
    availableComposerSubmitShortcuts.has(value as ComposerSubmitShortcut)
    ? value as ComposerSubmitShortcut
    : defaultComposerSubmitShortcut;
}

export function useComposerSubmitShortcut(accountId: string) {
  return normalizeComposerSubmitShortcut(
    useConversationPreferences(accountId).composer_submit_shortcut
  );
}

export function writeComposerSubmitShortcut(
  accountId: string,
  shortcut: ComposerSubmitShortcut
) {
  const normalized = normalizeComposerSubmitShortcut(shortcut);
  writeConversationPreferences(accountId, {
    ...readConversationPreferences(accountId),
    composer_submit_shortcut: normalized
  });
  return normalized;
}
