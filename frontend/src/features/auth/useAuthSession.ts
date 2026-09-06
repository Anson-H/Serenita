import { advanceAuthLifecycle, captureAuthContext, isAuthContextCurrent, setAuthenticatedAccount } from "../../api/authLifecycle";
import { useCallback, useEffect, useRef, useState } from "react";

import { publishAuthSessionChange, subscribeAuthSessionChanges } from "../../api/authSessionEvents";
import type { AuthenticatedSession, AuthSession } from "../../api/types";
import { checkSession, signIn, signOut as requestSignOut, signUp } from "../../api/authApi";

const MAX_BROWSER_TIMEOUT_MS = 2_147_000_000;
const EXPIRED_SESSION_RETRY_MS = 60_000;

export function useAuthSession() {
  const [session, setSession] = useState<AuthSession>({ authenticated: false });
  const [checkingSession, setCheckingSession] = useState(true);
  const mountedRef = useRef(false);
  const requestSequenceRef = useRef(0);

  const refreshSession = useCallback(async (blocking = false) => {
    const requestSequence = ++requestSequenceRef.current;
    if (blocking) setCheckingSession(true);
    try {
      const nextSession = await checkSession();
      if (!mountedRef.current || requestSequence !== requestSequenceRef.current) return;
      setAuthenticatedAccount(nextSession.authenticated ? nextSession.account_id : null);
      setSession(nextSession);
    } catch {
      if (!mountedRef.current || requestSequence !== requestSequenceRef.current) return;
      if (blocking) { setAuthenticatedAccount(null); setSession({ authenticated: false }); }
    } finally {
      if (mountedRef.current && requestSequence === requestSequenceRef.current) {
        setCheckingSession(false);
      }
    }
  }, []);

  useEffect(() => {
    mountedRef.current = true;
    const unsubscribe = subscribeAuthSessionChanges((change) => {
      if (change.kind === "invalidated") {
        advanceAuthLifecycle(null);
        requestSequenceRef.current += 1;
        setSession({ authenticated: false });
        setCheckingSession(false);
        return;
      }
      void refreshSession(false);
    });
    const onFocus = () => { void refreshSession(false); };
    const onVisibilityChange = () => {
      if (document.visibilityState === "visible") void refreshSession(false);
    };

    void refreshSession(true);
    window.addEventListener("focus", onFocus);
    document.addEventListener("visibilitychange", onVisibilityChange);
    return () => {
      mountedRef.current = false;
      requestSequenceRef.current += 1;
      unsubscribe();
      window.removeEventListener("focus", onFocus);
      document.removeEventListener("visibilitychange", onVisibilityChange);
    };
  }, [refreshSession]);

  useEffect(() => {
    if (!session.authenticated || !session.expires_at) return;
    const expiresAt = Date.parse(session.expires_at);
    if (!Number.isFinite(expiresAt)) return;

    let cancelled = false;
    let timeoutId: number | undefined;
    const scheduleValidation = () => {
      const remaining = expiresAt - Date.now();
      if (remaining <= 0) {
        void refreshSession(false).finally(() => {
          if (!cancelled) {
            timeoutId = window.setTimeout(scheduleValidation, EXPIRED_SESSION_RETRY_MS);
          }
        });
        return;
      }
      timeoutId = window.setTimeout(
        scheduleValidation,
        Math.min(remaining + 50, MAX_BROWSER_TIMEOUT_MS)
      );
    };
    scheduleValidation();
    return () => {
      cancelled = true;
      if (timeoutId !== undefined) window.clearTimeout(timeoutId);
    };
  }, [refreshSession, session]);

  async function authenticate(
    mode: "sign_in" | "sign_up",
    account: string,
    accountName: string,
    password: string,
    confirmPassword: string
  ) {
    advanceAuthLifecycle();
    const result = mode === "sign_in"
      ? await signIn(account, password)
      : await signUp(account, accountName, password, confirmPassword);
    requestSequenceRef.current += 1;
    setAuthenticatedAccount(result.account_id);
    setSession(result);
    setCheckingSession(false);
    publishAuthSessionChange("refresh");
  }

  async function signInWithPassword(account: string, password: string) {
    return authenticate("sign_in", account, "", password, "");
  }

  async function signUpWithPassword(account: string, accountName: string, password: string, confirmPassword: string) {
    return authenticate("sign_up", account, accountName, password, confirmPassword);
  }

  async function signOut() {
    advanceAuthLifecycle();
    requestSequenceRef.current += 1;
    const context = captureAuthContext();
    try {
      await requestSignOut();
    } finally {
      if (isAuthContextCurrent(context)) {
      requestSequenceRef.current += 1;
      setAuthenticatedAccount(null);
      setSession({ authenticated: false });
      setCheckingSession(false);
      publishAuthSessionChange("invalidated");
      }
    }
  }

  function updateAccountProfile(nextSession: AuthenticatedSession) {
    requestSequenceRef.current += 1;
    setAuthenticatedAccount(nextSession.authenticated ? nextSession.account_id : null);
      setSession(nextSession);
    setCheckingSession(false);
    publishAuthSessionChange("refresh");
  }

  return {
    checkingSession,
    session,
    refreshSession,
    signInWithPassword,
    signUpWithPassword,
    signOut,
    updateAccountProfile
  };
}
