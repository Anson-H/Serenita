

type WebProviderSummary = {
  provider_id: "tavily" | "exa";
  provider_name: string;
  api_url: string;
  has_api_key: boolean;
};

export type WebAccessSettings = {
  is_enabled: boolean;
  active_provider_id: "tavily" | "exa";
  providers: WebProviderSummary[];
};

export type WebProviderTestResponse = {
  provider_id: "tavily" | "exa";
  reachable: boolean;
  message: string;
};
