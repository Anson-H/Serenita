

export type ProviderSummary = {
  provider_id: string;
  provider_name: string;
  default_api_url: string;
  default_official_url: string;
  native_attachment_mime_types: string[];
  api_url: string;
  official_url: string;
  has_api_key: boolean;
  is_configured: boolean;
};

export type ProviderListResponse = {
  providers: ProviderSummary[];
};

export type ProviderTestResponse = {
  provider_id: string;
  reachable: boolean;
  message: string;
};

export type CredentialRevealResponse = {
  provider_id: string;
  api_key: string;
};

export type RemoteModel = {
  remote_model_id: string;
  model_name: string;
  created_at?: number | null;
  supports_text: boolean;
  file_mime_types: string[];
  thinking_modes: string[];
  supports_tool_calling: boolean;
  capability_profiles: ModelCapabilityProfiles;
  context_window_tokens: number | null;
  max_output_tokens: number | null;
};

export type AddedModel = RemoteModel & {
  model_id: string;
  provider_id: string;
};

export type ModelUpdatePayload = {
  model_name?: string;
  thinking_modes?: string[];
  capability_profiles?: ModelCapabilityProfiles;
  context_window_tokens?: number | null;
  max_output_tokens?: number | null;
};

type ModelCapabilityAvailability = "available" | "unavailable" | "unverified";

export type ModelModeCapabilityProfile = {
  availability: ModelCapabilityAvailability;
  supports_text: boolean;
  file_mime_types: string[];
  supports_tool_calling: boolean;
};

export type ModelCapabilityProfiles = {
  default_state: "thinking" | "non_thinking" | "unknown";
  non_thinking: ModelModeCapabilityProfile;
  thinking: ModelModeCapabilityProfile;
};

export type ModelCapabilityProbeStatus =
  | "supported"
  | "unsupported"
  | "unverified"
  | "not_applicable";

export type ModelCapabilityProbeChecks = Record<string, ModelCapabilityProbeStatus>;

export type ModelCapabilityProbeResponse = {
  model: AddedModel;
  metadata: {
    status: "refreshed" | "unavailable" | "not_found";
    message: string;
  };
  checks: {
    thinking_modes: ModelCapabilityProbeChecks;
    aggregate: ModelCapabilityProbeChecks;
    non_thinking: ModelCapabilityProbeChecks;
    thinking: ModelCapabilityProbeChecks;
  };
  errors: {
    thinking_modes: Record<string, string>;
    non_thinking: Record<string, string>;
    thinking: Record<string, string>;
  };
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
