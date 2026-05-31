import { useEffect, useState } from "react";

import { AuthSession } from "../../api/types";
import { checkSession, signIn, signOut as requestSignOut, signUp } from "../../api/authApi";
import { clearSessionToken, saveSessionToken } from "../../api/sessionToken";

export function useAuthSession() {
  const [session, setSession] = useState<AuthSession>({ authenticated: false });
  const [checkingSession, setCheckingSession] = useState(true);

  useEffect(() => {
    void refreshSession();
  }, []);

  async function refreshSession() {
    setCheckingSession(true);
    try {
      const nextSession = await checkSession();
      setSession(nextSession);
    } catch {
      clearSessionToken();
      setSession({ authenticated: false });
    } finally {
      setCheckingSession(false);
    }
  }

  async function authenticate(
    mode: "sign_in" | "sign_up",
    account: string,
    userName: string,
    password: string,
    confirmPassword: string
  ) {
    const result =
      mode === "sign_in"
        ? await signIn(account, password)
        : await signUp(account, userName, password, confirmPassword);
    saveSessionToken(result.session_token);
    setSession({
      authenticated: true,
      account: result.account,
      user_name: result.user_name,
      expires_at: result.expires_at,
      session_token: result.session_token
    });
    return result;
  }

  async function signInWithPassword(account: string, password: string) {
    return authenticate("sign_in", account, "", password, "");
  }

  async function signUpWithPassword(account: string, userName: string, password: string, confirmPassword: string) {
    return authenticate("sign_up", account, userName, password, confirmPassword);
  }

  async function signOut() {
    try {
      await requestSignOut();
    } finally {
      clearSessionToken();
      setSession({ authenticated: false });
    }
  }

  function updateUserName(userName: string) {
    setSession((current) =>
      current.authenticated
        ? {
            ...current,
            user_name: userName
          }
        : current
    );
  }

  return {
    checkingSession,
    session,
    refreshSession,
    signInWithPassword,
    signUpWithPassword,
    signOut,
    updateUserName
  };
}
