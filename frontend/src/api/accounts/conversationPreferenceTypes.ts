

export type ComposerSubmitShortcut = "enter" | "modifier_enter";

export type BaseContextAssemblyType =
  | "system_prompt"
  | "tool_catalog"
  | "skill_catalog"
  | "runtime_context";

export type BaseContextAssemblyDisplayMode =
  | "hidden"
  | "every_step"
  | "conversation_start"
  | "turn_start";

export type ConversationContextDisplayType =
  | "current_user_message"
  | "conversation_history"
  | "model_tool_request"
  | "tool_observation"
  | "compacted_summary";

export type ToolExecutionDisplayType = "model_tool_request" | "tool_call";

export type ConversationPreferences = {
  composer_submit_shortcut: ComposerSubmitShortcut;
  base_context_display_modes: Record<
    BaseContextAssemblyType,
    BaseContextAssemblyDisplayMode
  >;
  is_context_window_usage_visible: boolean;
  is_related_content_visible: boolean;
  is_token_usage_visible: boolean;
  is_model_identity_visible: boolean;
  visible_context_types: ConversationContextDisplayType[];
  tool_display_types: ToolExecutionDisplayType[];
};
