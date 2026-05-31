const SESSION_TOKEN_KEY = "serenita_auth_session_token";
const LEGACY_SESSION_TOKEN_KEY = "serenita_session_token";

export function getSessionToken() {
  const token = window.localStorage.getItem(SESSION_TOKEN_KEY);
  if (token) {
    return token;
  }
  const legacyToken = window.localStorage.getItem(LEGACY_SESSION_TOKEN_KEY);
  if (legacyToken) {
    saveSessionToken(legacyToken);
    window.localStorage.removeItem(LEGACY_SESSION_TOKEN_KEY);
  }
  return legacyToken;
}

export function saveSessionToken(token: string) {
  window.localStorage.setItem(SESSION_TOKEN_KEY, token);
  window.localStorage.removeItem(LEGACY_SESSION_TOKEN_KEY);
}

export function clearSessionToken() {
  window.localStorage.removeItem(SESSION_TOKEN_KEY);
  window.localStorage.removeItem(LEGACY_SESSION_TOKEN_KEY);
}
