import {NotificationProvider} from "./features/notifications/NotificationProvider";
import { useEffect } from "react";
import { DeviceAuthorizationLogin } from "./features/auth/DeviceAuthorizationLogin";
import { ModelOnboarding } from "./features/modelConfiguration/ModelOnboarding";
import { DEVICE_AUTH_PATH, NOT_FOUND_PATH } from "./app/routes";
import { DeploymentProvider, useDeployment } from "./app/DeploymentContext";
import { isSettingsRoute, readSettingsRoute, settingsPath } from "./app/settingsRoutes";
import { EmptyState } from "./components/EmptyState";
import { RegenerateIcon } from "./components/icons";

import { PatientShell } from "./app/PatientShell";
import {
  APP_PATH,
  healthPathForMember,
  memoryPath,
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
  return <DeploymentProvider><Application /></DeploymentProvider>;
}

function Application() {
  useScrollbarMetrics();
  const deployment = useDeployment();
  const local = deployment.mode === "self_hosted";
  const homePath = APP_PATH;
  function postLoginPath(): RoutePath {
    const target = sessionStorage.getItem("serenita-login-return");
    return !local && target && isSettingsRoute(target) ? target as RoutePath : homePath;
  }
  const { route, navigateTo: navigateBrowserTo } = useBrowserRoute();
  const deviceRoute = route.split("?")[0] === DEVICE_AUTH_PATH;
  const deviceCode = !local && (isAuthRoute(route) || deviceRoute)
    ? new URLSearchParams(window.location.search).get("user_code") : null;
  const unavailableRoute = route === NOT_FOUND_PATH || (deviceRoute && !deviceCode) || (local && readSettingsRoute(route)?.section === "account");
  const {
    checkingSession,
    session,
    signInWithPassword,
    signUpWithPassword,
    signOut,
    updateAccountProfile,
    refreshSession,
    sessionError,
    enterGuest
  } = useAuthSession();

  function navigateTo(path: RoutePath, replace = false) {
    navigateBrowserTo(path, replace);
  }

  useEffect(() => {
    if (checkingSession) {
      return;
    }
    if (unavailableRoute) return;
    if (deviceCode) return;
    if (local) {
      if (isAuthRoute(route)) navigateTo(APP_PATH, true);
      return;
    }
    if (!session.authenticated) {
      if (isSettingsRoute(route)) sessionStorage.setItem("serenita-login-return", route);
      if (!isAuthRoute(route) || window.location.pathname !== route) {
        navigateTo(SIGN_IN_PATH, true);
      }
      return;
    }
    if (isAuthRoute(route)) {
      navigateTo(postLoginPath(), true);
    }
    if (!isAuthRoute(route)) sessionStorage.removeItem("serenita-login-return");
  }, [checkingSession, route, session.authenticated, local, unavailableRoute, deviceCode]);

  function renderRoute() {
    if (checkingSession) {
      return (
        <main className="login-page">
          <section className="auth-panel">
            <div className="brand-name">Serenita</div>
            <p className="status-message testing">正在打开 Serenita…</p>
          </section>
        </main>
      );
    }

    if (unavailableRoute) return <main className="login-page"><section className="auth-panel"><EmptyState layout="inline" title="页面不存在" /><button className="control" type="button" onClick={() => navigateTo(homePath)}>返回 Serenita</button></section></main>;

    if (deviceCode) return <DeviceAuthorizationLogin key={deviceCode} code={deviceCode} route={route}
      accountId={session.authenticated ? session.account_id : null} onNavigate={navigateTo}
      accountName={session.authenticated ? session.account_name : ""} account={session.authenticated ? session.account : ""}
      onSignIn={(account, password) => signInWithPassword(account, password, deviceCode)}
      onSignUp={(account, name, password, confirm) => signUpWithPassword(account, name, password, confirm, deviceCode)} />;

    if (!session.authenticated && local) return <main className="login-page"><section className="auth-panel"><EmptyState layout="inline" title="本地工作区暂不可用" description={sessionError || "请检查后端服务和本地工作区配置。"} /><button className="control" type="button" onClick={() => void refreshSession(true)}><RegenerateIcon /><span>重试</span></button></section></main>;

    if (!session.authenticated) {
      return (
        <AuthPage
          mode={route === SIGN_UP_PATH ? "sign_up" : "sign_in"}
          onModeChange={(path) => navigateTo(path)}
          onSignIn={async (account, password) => {
            await signInWithPassword(account, password);
            navigateTo(postLoginPath());
          }}
          onSignUp={async (account, accountName, password, confirmPassword) => {
            await signUpWithPassword(account, accountName, password, confirmPassword);
            navigateTo(postLoginPath());
          }}
          onGuestEntry={async () => {
            await enterGuest();
            navigateTo(postLoginPath());
          }}
        />
      );
    }

    return (
      <MemberProvider key={session.account_id} onStartMember={(destination, memberId) => navigateTo(destination.type === "health"
        && memberId ? healthPathForMember(memberId)
        : destination.type === "memory" && memberId ? memoryPath(memberId)
        : destination.type === "reports" && memberId ? destination.reportId ? reportPathForReport(destination.reportId, memberId) : REPORTS_PATH
        : APP_PATH)}>
      <NotificationProvider>
      {local ? <ModelOnboarding onSettings={() => navigateTo(settingsPath({ section: "providers", page: "root" }))} /> : null}
      <WorkspacePage
        route={route}
        onNavigate={navigateTo}
        session={session}
        onSignOut={signOut}
        onAccountProfileChange={updateAccountProfile}
        ShellComponent={PatientShell}
      />
      </NotificationProvider>
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
