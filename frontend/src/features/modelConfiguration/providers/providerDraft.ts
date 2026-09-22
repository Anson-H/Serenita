export type ProviderDraft = {
  officialUrl: string;
  apiUrl: string;
  apiKey: string;
};

export function draftsMatch(left?: ProviderDraft, right?: ProviderDraft) {
  return (
    Boolean(left && right) &&
    left?.officialUrl === right?.officialUrl &&
    left?.apiUrl === right?.apiUrl &&
    left?.apiKey === right?.apiKey
  );
}

