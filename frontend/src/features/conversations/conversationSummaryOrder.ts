import {
  type ConversationSummary
} from "../../api/client";

export function compareConversationSummaries(
  left: ConversationSummary,
  right: ConversationSummary
) {
  if (left.is_pinned !== right.is_pinned) {
    return left.is_pinned ? -1 : 1;
  }
  return Date.parse(right.last_active_at) - Date.parse(left.last_active_at);
}
