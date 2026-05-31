export type ProviderSummary = {
  provider_id: string;
  provider_name: string;
  default_base_url?: string;
  default_official_url?: string;
  base_url?: string;
  official_url?: string;
  api_key?: string;
  configured: boolean;
  default: boolean;
};

export type ProviderListResponse = {
  providers: ProviderSummary[];
};

export type ProviderTestResponse = {
  provider_id: string;
  reachable: boolean;
  message: string;
};

export type RemoteModel = {
  remote_model_id: string;
  model_name: string;
  supports_text: boolean;
  file_mime_types: string[];
  thinking_modes: string[];
  supports_tool_calling: boolean;
  supports_json_output: boolean;
  context_window_tokens: number | null;
  max_output_tokens: number | null;
};

export type AddedModel = RemoteModel & {
  model_id: string;
  provider_id: string;
};

export type ModelDefaults = {
  chat: AddedModel | null;
  title: AddedModel | null;
  vision_parse: AddedModel | null;
  compact: AddedModel | null;
};

export type ModelDefaultsResponse = {
  defaults: ModelDefaults;
};

export type AuthSession =
  | {
      authenticated: false;
    }
  | {
      authenticated: true;
      account: string;
      user_name: string;
      expires_at?: string;
      session_token?: string;
    };

export type AuthResponse = {
  authenticated: true;
  account: string;
  user_name: string;
  session_token: string;
  expires_at?: string;
};

export type ConversationSummary = {
  session_id: string;
  title: string;
  last_message_preview: string;
  created_at: string;
  last_active_at: string;
};

export type ConversationMessage = {
  message_id: string;
  turn_id: string;
  parent_message_id: string | null;
  role: "user" | "assistant" | "thinking";
  model_id?: string;
  thinking_mode?: string;
  duration_ms?: number;
  content: string;
  context_resources?: Array<Record<string, unknown>>;
  status?: string;
  created_at: string;
};

export type ConversationDetail = {
  session_id: string;
  account: string;
  title: string;
  pending_turns: Array<Record<string, unknown>>;
  active_path_message_ids: string[];
  messages: ConversationMessage[];
  all_messages?: ConversationMessage[];
};

export type SendMessageResponse = {
  session_id: string;
  turn_id: string;
  user_message_id: string;
  assistant_message_id: string;
  assistant_parent_message_id?: string | null;
  thinking_message_id?: string | null;
  model_id: string;
  message_status: string;
  stream_id: string;
  content: string;
  context_resources?: Array<Record<string, unknown>>;
  created_at: string;
};

export type CancelTurnResponse = {
  session_id: string;
  turn_id: string;
  status: "cancelled";
  preserve_partial: boolean;
  stream_id: string;
  assistant_message_id?: string | null;
  thinking_message_id?: string | null;
};

export type ConversationStreamEvent =
  | {
      event: "thinking_delta" | "content_delta";
      data: {
        session_id: string;
        turn_id: string;
        message_id?: string;
        delta: string;
      };
    }
  | {
      event: "completed";
      data: {
        session_id: string;
        turn_id: string;
        assistant_message_id?: string | null;
        thinking_message_id?: string | null;
      };
    }
  | {
      event: "failed";
      data: {
        session_id: string;
        turn_id: string;
        code?: string;
        message?: string;
      };
    }
  | {
      event: "cancelled";
      data: {
        session_id: string;
        turn_id: string;
        code?: string;
        message?: string;
      };
    };

export type Favorite = {
  favorite_id: string;
  source_type: string;
  source_session_id: string;
  source_id: string;
  title: string;
  content_summary: string;
  content_snapshot?: string;
  source_available?: boolean;
  tags: string[];
  created_at: string;
  updated_at?: string;
};

export type UploadedResource = {
  resource_id: string;
  name: string;
  mime_type: string;
  size_bytes: number;
  usage_status: string;
};
