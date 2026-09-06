import { FormEvent, useEffect, useState } from "react";

import { SIGN_IN_PATH, SIGN_UP_PATH, type RoutePath } from "../../app/routes";
import { SecretInput } from "../../components/SecretInput";
import { useStatusNotification } from "../../components/StatusNotificationCenter";
import {
  formTextValue,
  keepTextControlFocused,
  syncCommittedText
} from "../../utils/inputMethod";
import { validateAccountNameForSignUp } from "./validation";

type AuthPageProps = {
  mode: "sign_in" | "sign_up";
  onModeChange: (path: RoutePath) => void;
  onSignIn: (account: string, password: string) => Promise<void>;
  onSignUp: (account: string, accountName: string, password: string, confirmPassword: string) => Promise<void>;
};

type AuthMode = "sign_in" | "sign_up";

export function AuthPage({ mode, onModeChange, onSignIn, onSignUp }: AuthPageProps) {
  const [authMode, setAuthMode] = useState<AuthMode>(mode);
  const [authAccount, setAuthAccount] = useState("");
  const [authAccountName, setAuthAccountName] = useState("");
  const [authPassword, setAuthPassword] = useState("");
  const [authConfirmPassword, setAuthConfirmPassword] = useState("");
  const [authError, setAuthError] = useState("");
  const [authSubmitting, setAuthSubmitting] = useState(false);

  useStatusNotification(authError, {
    id: "authentication-error",
    title: "认证未完成",
    tone: "error"
  });

  useEffect(() => {
    setAuthMode(mode);
  }, [mode]);

  async function submitAuth(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setAuthError("");
    const submittedAccount = formTextValue(event.currentTarget, "account", authAccount);
    const submittedAccountName = formTextValue(event.currentTarget, "account-name", authAccountName);
    const submittedPassword = formTextValue(event.currentTarget, "password", authPassword);
    const submittedConfirmPassword = formTextValue(
      event.currentTarget,
      "confirm-password",
      authConfirmPassword
    );

    const validationMessage = authMode === "sign_up" ? validateAccountNameForSignUp(submittedAccountName) : "";
    if (validationMessage) {
      setAuthError(validationMessage);
      return;
    }

    setAuthSubmitting(true);

    try {
      if (authMode === "sign_in") {
        await onSignIn(submittedAccount, submittedPassword);
      } else {
        await onSignUp(
          submittedAccount,
          submittedAccountName,
          submittedPassword,
          submittedConfirmPassword
        );
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
              <p>用户标识：1-20 位英文、数字、下划线或短横线，登录时不区分大小写。</p>
              <p>账号名称：1-50 个字符，允许 Unicode 和内部空格。</p>
              <p>密码：不能为空，请妥善保存；确认密码必须完全一致。</p>
            </div>
          ) : null}
          <label>
            用户标识
            <input
              autoComplete="username"
              name="account"
              value={authAccount}
              onChange={(event) => setAuthAccount(event.target.value)}
              onCompositionEnd={(event) => syncCommittedText(event, setAuthAccount)}
            />
          </label>
          {authMode === "sign_up" ? (
            <label>
              账号名称
              <input name="account-name" value={authAccountName} onChange={(event) => setAuthAccountName(event.target.value)} onCompositionEnd={(event) => syncCommittedText(event, setAuthAccountName)} />
            </label>
          ) : null}
          <div className="secret-field">
            <label htmlFor="auth-password">密码</label>
            <SecretInput
              autoComplete={authMode === "sign_in" ? "current-password" : "new-password"}
              id="auth-password"
              labelForAction="密码"
              name="password"
              value={authPassword}
              onChange={(event) => setAuthPassword(event.target.value)}
              onCompositionEnd={(event) => syncCommittedText(event, setAuthPassword)}
            />
          </div>
          {authMode === "sign_up" ? (
            <div className="secret-field">
              <label htmlFor="auth-confirm-password">确认密码</label>
              <SecretInput
                autoComplete="new-password"
                id="auth-confirm-password"
                labelForAction="确认密码"
                name="confirm-password"
                value={authConfirmPassword}
                onChange={(event) => setAuthConfirmPassword(event.target.value)}
                onCompositionEnd={(event) => syncCommittedText(event, setAuthConfirmPassword)}
              />
            </div>
          ) : null}
          <button className="control control--primary command-button control-primary" disabled={authSubmitting} onMouseDown={keepTextControlFocused} type="submit">
            {authSubmitting ? "处理中..." : authMode === "sign_in" ? "登录" : "注册并进入"}
          </button>
        </form>
      </section>
    </main>
  );
}
