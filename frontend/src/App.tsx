import { useEffect } from "react";

import { PatientShell } from "./app/PatientShell";
import {
  APP_PATH,
  healthPathForMember,
  isAuthRoute,
  reportPathForReport,
  REPORTS_PATH,
  SIGN_IN_PATH,
  SIGN_UP_PATH,
  type RoutePath
} from "./app/routes";
import { useBrowserRoute } from "./app/useBrowserRoute";
import { useScrollbarMetrics } from "./app/useScrollbarMetrics";
import { WorkspacePage } from "./app/workspace/WorkspacePage";
import { StatusNotificationCenter } from "./components/StatusNotificationCenter";
import { AuthPage } from "./features/auth/AuthPage";
import { useAuthSession } from "./features/auth/useAuthSession";
import { MemberProvider } from "./features/members/MemberProvider";

export function App() {
  useScrollbarMetrics();
  const { route, navigateTo: navigateBrowserTo } = useBrowserRoute();
  const {
    checkingSession,
    session,
    signInWithPassword,
    signUpWithPassword,
    signOut,
    updateAccountProfile
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
          onSignUp={async (account, accountName, password, confirmPassword) => {
            await signUpWithPassword(account, accountName, password, confirmPassword);
            navigateTo(APP_PATH);
          }}
        />
      );
    }

    return (
      <MemberProvider key={session.account_id} onStartMember={(destination, memberId) => navigateTo(destination.type === "health"
        && memberId ? healthPathForMember(memberId)
        : destination.type === "reports" && memberId ? destination.reportId ? reportPathForReport(destination.reportId, memberId) : REPORTS_PATH
        : APP_PATH)}>
      <WorkspacePage
        route={route}
        onNavigate={navigateTo}
        session={session}
        onSignOut={signOut}
        onAccountProfileChange={updateAccountProfile}
        ShellComponent={PatientShell}
      />
      </MemberProvider>
    );
  }

  return (
    <>
      {renderRoute()}
      <StatusNotificationCenter />
    </>
  );
}
