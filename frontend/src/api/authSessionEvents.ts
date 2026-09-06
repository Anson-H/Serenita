export type AuthSessionChangeKind = "invalidated" | "refresh";

type AuthSessionChange = {
  kind: AuthSessionChangeKind;
  nonce: string;
  timestamp: number;
};

const AUTH_SESSION_EVENT = "serenita:auth-session-changed";
const AUTH_SESSION_STORAGE_KEY = "serenita:auth-session-change";
let authSessionChangeSequence = 0;

function createAuthSessionChange(kind: AuthSessionChangeKind): AuthSessionChange {
  authSessionChangeSequence += 1;
  return {
    kind,
    nonce: `${Date.now()}-${authSessionChangeSequence}-${Math.random().toString(36).slice(2)}`,
    timestamp: Date.now()
  };
}

function parseAuthSessionChange(value: unknown): AuthSessionChange | null {
  if (!value || typeof value !== "object") return null;
  const candidate = value as Partial<AuthSessionChange>;
  if (
    (candidate.kind !== "invalidated" && candidate.kind !== "refresh") ||
    typeof candidate.nonce !== "string" ||
    typeof candidate.timestamp !== "number"
  ) {
    return null;
  }
  return candidate as AuthSessionChange;
}

export function publishAuthSessionChange(kind: AuthSessionChangeKind) {
  if (typeof window === "undefined") return;
  const change = createAuthSessionChange(kind);
  window.dispatchEvent(new CustomEvent<AuthSessionChange>(AUTH_SESSION_EVENT, { detail: change }));
  try {
    window.localStorage.setItem(AUTH_SESSION_STORAGE_KEY, JSON.stringify(change));
  } catch {
    // The current-tab event still keeps this page correct when storage is unavailable.
  }
}

export function publishAuthInvalidation(status: number, code?: string | null) {
  if (status !== 401 || code === "SIGN_IN_FAILED") return;
  publishAuthSessionChange("invalidated");
}

export function subscribeAuthSessionChanges(
  listener: (change: AuthSessionChange) => void
) {
  if (typeof window === "undefined") return () => undefined;

  const onCurrentTabChange = (event: Event) => {
    const change = parseAuthSessionChange((event as CustomEvent<unknown>).detail);
    if (change) listener(change);
  };
  const onOtherTabChange = (event: StorageEvent) => {
    if (event.key !== AUTH_SESSION_STORAGE_KEY || !event.newValue) return;
    try {
      const change = parseAuthSessionChange(JSON.parse(event.newValue));
      if (change) listener({ ...change, kind: "refresh" });
    } catch {
      // Ignore malformed browser storage written outside Serenita.
    }
  };

  window.addEventListener(AUTH_SESSION_EVENT, onCurrentTabChange);
  window.addEventListener("storage", onOtherTabChange);
  return () => {
    window.removeEventListener(AUTH_SESSION_EVENT, onCurrentTabChange);
    window.removeEventListener("storage", onOtherTabChange);
  };
}
