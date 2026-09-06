

export type AuthenticatedSession = {
  account_id: string;
  authenticated: true;
  account: string;
  account_name: string;
  expires_at: string;
};

export type AuthSession =
  | { authenticated: false }
  | AuthenticatedSession;
