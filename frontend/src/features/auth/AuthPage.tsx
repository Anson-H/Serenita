import { FormEvent, useEffect, useState } from "react";

import { SIGN_IN_PATH, SIGN_UP_PATH, type RoutePath } from "../../app/routes";
import { SecretInput } from "../../components/SecretInput";
import { validateUserNameForSignUp } from "./validation";

type AuthPageProps = {
  mode: "sign_in" | "sign_up";
  onModeChange: (path: RoutePath) => void;
  onSignIn: (account: string, password: string) => Promise<void>;
  onSignUp: (account: string, userName: string, password: string, confirmPassword: string) => Promise<void>;
};

type AuthMode = "sign_in" | "sign_up";

export function AuthPage({ mode, onModeChange, onSignIn, onSignUp }: AuthPageProps) {
  const [authMode, setAuthMode] = useState<AuthMode>(mode);
  const [authAccount, setAuthAccount] = useState("");
  const [authUserName, setAuthUserName] = useState("");
  const [authPassword, setAuthPassword] = useState("");
  const [authConfirmPassword, setAuthConfirmPassword] = useState("");
  const [authError, setAuthError] = useState("");
  const [authSubmitting, setAuthSubmitting] = useState(false);

  useEffect(() => {
    setAuthMode(mode);
  }, [mode]);

  async function submitAuth(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setAuthError("");

    const validationMessage = authMode === "sign_up" ? validateUserNameForSignUp(authUserName) : "";
    if (validationMessage) {
      setAuthError(validationMessage);
      return;
    }

    setAuthSubmitting(true);

    try {
      if (authMode === "sign_in") {
        await onSignIn(authAccount, authPassword);
      } else {
        await onSignUp(authAccount, authUserName, authPassword, authConfirmPassword);
      }
      setAuthPassword("");
      setAuthConfirmPassword("");
    } catch (error) {
      setAuthError(error instanceof Error ? error.message : "认证失败");
    } finally {
      setAuthSubmitting(false);
    }
  }

  return (
    <main className="login-page">
      <section className="auth-panel">
        <div className="brand-block">
          <div className="brand-name">Serenita</div>
        </div>
        <div className="auth-switch" role="tablist" aria-label="认证方式">
          <button
            className={authMode === "sign_in" ? "workspace-tab active" : "workspace-tab"}
            onClick={() => onModeChange(SIGN_IN_PATH)}
            type="button"
          >
            登录
          </button>
          <button
            className={authMode === "sign_up" ? "workspace-tab active" : "workspace-tab"}
            onClick={() => onModeChange(SIGN_UP_PATH)}
            type="button"
          >
            注册
          </button>
        </div>

        <form className={authMode === "sign_in" ? "login-form" : "register-form"} onSubmit={submitAuth}>
          {authMode === "sign_up" ? (
            <div className="registration-guidance" role="note">
              <p>账号：1-20 位英文、数字、下划线或短横线，登录时不区分大小写。</p>
              <p>密码：不能为空，请妥善保存；确认密码必须完全一致。</p>
            </div>
          ) : null}
          <label>
            账号
            <input
              autoComplete="username"
              value={authAccount}
              onChange={(event) => setAuthAccount(event.target.value)}
            />
          </label>
          {authMode === "sign_up" ? (
            <label>
              用户名称
              <input value={authUserName} onChange={(event) => setAuthUserName(event.target.value)} />
            </label>
          ) : null}
          <div className="secret-field">
            <label htmlFor="auth-password">密码</label>
            <SecretInput
              autoComplete={authMode === "sign_in" ? "current-password" : "new-password"}
              id="auth-password"
              labelForAction="密码"
              value={authPassword}
              onChange={(event) => setAuthPassword(event.target.value)}
            />
          </div>
          {authMode === "sign_up" ? (
            <div className="secret-field">
              <label htmlFor="auth-confirm-password">确认密码</label>
              <SecretInput
                autoComplete="new-password"
                id="auth-confirm-password"
                labelForAction="确认密码"
                value={authConfirmPassword}
                onChange={(event) => setAuthConfirmPassword(event.target.value)}
              />
            </div>
          ) : null}
          <button className="command-button" disabled={authSubmitting} type="submit">
            {authSubmitting ? "处理中..." : authMode === "sign_in" ? "登录" : "注册并进入"}
          </button>
          {authError ? <p className="status-message error">{authError}</p> : null}
        </form>
      </section>
    </main>
  );
}
