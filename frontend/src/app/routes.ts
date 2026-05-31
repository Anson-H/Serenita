export const SIGN_IN_PATH = "/sign_in";
export const SIGN_UP_PATH = "/sign_up";
export const APP_PATH = "/";
export const FAVORITES_PATH = "/favorites";
export const SETTING_PATH = "/setting";
export const CHAT_PATH_PREFIX = "/chat/";

export type ChatRoutePath = `${typeof CHAT_PATH_PREFIX}${string}`;
export type RoutePath =
  | typeof SIGN_IN_PATH
  | typeof SIGN_UP_PATH
  | typeof APP_PATH
  | typeof FAVORITES_PATH
  | typeof SETTING_PATH
  | ChatRoutePath;

export function currentRoute(): RoutePath {
  if (window.location.pathname.startsWith(CHAT_PATH_PREFIX)) {
    return window.location.pathname as ChatRoutePath;
  }
  if (window.location.pathname === APP_PATH) {
    return APP_PATH;
  }
  if (window.location.pathname === FAVORITES_PATH) {
    return FAVORITES_PATH;
  }
  if (window.location.pathname === SETTING_PATH) {
    return SETTING_PATH;
  }
  if (window.location.pathname === SIGN_UP_PATH) {
    return SIGN_UP_PATH;
  }
  return SIGN_IN_PATH;
}

export function chatPathForSession(sessionId: string): ChatRoutePath {
  return `${CHAT_PATH_PREFIX}${encodeURIComponent(sessionId)}` as ChatRoutePath;
}

export function sessionIdFromChatPath(path: string) {
  if (!path.startsWith(CHAT_PATH_PREFIX)) {
    return null;
  }
  const encodedSessionId = path.slice(CHAT_PATH_PREFIX.length);
  if (!encodedSessionId) {
    return null;
  }
  try {
    return decodeURIComponent(encodedSessionId);
  } catch {
    return encodedSessionId;
  }
}

export function isAuthRoute(path: RoutePath) {
  return path === SIGN_IN_PATH || path === SIGN_UP_PATH;
}
