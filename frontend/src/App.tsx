import { useEffect } from "react";

import {
  APP_PATH,
  SIGN_IN_PATH,
  SIGN_UP_PATH,
  isAuthRoute,
  type RoutePath
} from "./app/routes";
import { PatientShell } from "./app/PatientShell";
import { useBrowserRoute } from "./app/useBrowserRoute";
import { AuthPage } from "./features/auth/AuthPage";
import { useAuthSession } from "./features/auth/useAuthSession";
import { WorkspacePage } from "./features/conversations/WorkspacePage";

export function App() {
  const { route, navigateTo: navigateBrowserTo } = useBrowserRoute();
  const {
    checkingSession,
    session,
    signInWithPassword,
    signUpWithPassword,
    signOut,
    updateUserName
  } = useAuthSession();

  function navigateTo(path: RoutePath, replace = false) {
    navigateBrowserTo(path, replace);
  }

  useEffect(() => {
    if (checkingSession) {
      return;
    }
    if (!session.authenticated) {
      if (!isAuthRoute(route) || window.location.pathname !== route) {
        navigateTo(SIGN_IN_PATH, true);
      }
      return;
    }
    if (isAuthRoute(route)) {
      navigateTo(APP_PATH, true);
    }
  }, [checkingSession, route, session.authenticated]);

  function renderRoute() {
    if (checkingSession) {
      return (
        <main className="login-page">
          <section className="auth-panel">
            <div className="brand-name">Serenita</div>
            <p className="status-message testing">正在恢复登录态...</p>
          </section>
        </main>
      );
    }

    if (!session.authenticated) {
      return (
        <AuthPage
          mode={route === SIGN_UP_PATH ? "sign_up" : "sign_in"}
          onModeChange={(path) => navigateTo(path)}
          onSignIn={async (account, password) => {
            await signInWithPassword(account, password);
            navigateTo(APP_PATH);
          }}
          onSignUp={async (account, userName, password, confirmPassword) => {
            await signUpWithPassword(account, userName, password, confirmPassword);
            navigateTo(APP_PATH);
          }}
        />
      );
    }

    return (
      <WorkspacePage
        route={route}
        onNavigate={navigateTo}
        session={session}
        onSignOut={signOut}
        onUserNameChange={updateUserName}
        ShellComponent={PatientShell}
      />
    );
  }

  return renderRoute();
}
