import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { request } from "../../api/transport/request";
import { DEVICE_AUTH_PATH, SIGN_IN_PATH, SIGN_UP_PATH, deviceAuthorizationPath, deviceLoginPath, type RoutePath } from "../../app/routes";
import { LoadingIcon, UserIcon } from "../../components/icons";
import { AuthPage } from "./AuthPage";

type DeviceStatus = { status: "pending" | "approved" | "consumed" | "denied" | "expired"; expires_at?: string };

export function DeviceAuthorizationLogin({ code, route, accountId, accountName, account, onNavigate, onSignIn, onSignUp }: {
  code: string;
  route: RoutePath;
  accountId: string | null;
  accountName: string;
  account: string;
  onNavigate: (path: RoutePath, replace?: boolean) => void;
  onSignIn: (account: string, password: string) => Promise<void>;
  onSignUp: (account: string, accountName: string, password: string, confirmPassword: string) => Promise<void>;
}) {
  const [returnUrl] = useState(() => {
    const key = `serenita-authorization-return:${code}`;
    try {
      const target = new URLSearchParams(window.location.hash.slice(1)).get("return_to") || sessionStorage.getItem(key);
      if (!target) return null;
      const url = new URL(target);
      if (!["http:", "https:"].includes(url.protocol) || url.username || url.password || url.pathname !== "/setting/providers/serenita") return null;
      url.search = ""; url.hash = "";
      sessionStorage.setItem(key, url.href);
      return url.href;
    } catch { return null; }
  });
  function returnToWorkspace() {
    window.close();
    // A manually opened tab may not permit close; return to its source workspace.
    if (returnUrl) window.setTimeout(() => window.location.replace(returnUrl), 100);
  }
  const [status, setStatus] = useState<DeviceStatus | null>(null);
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState<"approved" | "denied" | null>(null);
  const [error, setError] = useState("");
  const [readError, setReadError] = useState("");
  const operating = useRef(false);
  const sequence = useRef(0);
  const mounted = useRef(true);
  const latestStatus = useRef<DeviceStatus | null>(null);
  const reading = useRef<AbortController | null>(null);
  const terminal = done || (status && status.status !== "pending" ? status.status : null);

  const refresh = useCallback(async () => {
    if (operating.current || reading.current) return;
    const expires = latestStatus.current?.expires_at;
    if (latestStatus.current?.status === "pending" && expires && Date.parse(expires) <= Date.now()) {
      setStatus({ status: "expired" }); return;
    }
    const ticket = ++sequence.current;
    const controller = new AbortController();
    reading.current = controller;
    const timeout = window.setTimeout(() => controller.abort(), 15000);
    try {
      const value = await request<DeviceStatus>(`/serenita/device/status?user_code=${encodeURIComponent(code)}`, { signal: controller.signal });
      if (mounted.current && ticket === sequence.current && !operating.current) { latestStatus.current = value; setStatus(value); setReadError(""); }
    } catch (cause) {
      if (mounted.current && ticket === sequence.current && !operating.current) setReadError(controller.signal.aborted ? "授权状态读取超时，请重试。" : cause instanceof Error ? cause.message : "授权状态读取失败。");
    } finally { window.clearTimeout(timeout); if (reading.current === controller) reading.current = null; }
  }, [code]);

  useEffect(() => {
    mounted.current = true;
    if (terminal) return () => { mounted.current = false; sequence.current++; };
    void refresh();
    const timer = window.setInterval(() => { if (document.visibilityState === "visible") void refresh(); }, 2000);
    const onFocus = () => void refresh();
    window.addEventListener("focus", onFocus);
    document.addEventListener("visibilitychange", onFocus);
    return () => { mounted.current = false; sequence.current++; reading.current?.abort(); reading.current = null; window.clearInterval(timer); window.removeEventListener("focus", onFocus); document.removeEventListener("visibilitychange", onFocus); };
  }, [refresh, terminal]);

  // Final authority stays on the server, including sign-in/registration. The
  // refresh above only removes stale controls; it cannot authorize a request.
  async function complete(operation: () => Promise<unknown>, result: "approved" | "denied") {
    if (operating.current) return;
    operating.current = true; sequence.current++; setBusy(true); setError("");
    try {
      await operation();
      if (mounted.current) { setDone(result); returnToWorkspace(); }
    } catch (cause) {
      if (mounted.current) setError(cause instanceof Error ? cause.message : "授权未完成，请重试。");
      throw cause;
    } finally {
      operating.current = false;
      if (mounted.current) { setBusy(false); void refresh(); }
    }
  }

  const retry = readError ? <><p className="content-description" role="alert">{readError}</p><button className="control" type="button" disabled={busy} onClick={() => void refresh()}>重新检查授权状态</button></> : null;
  const shell = (content: ReactNode) => <main className="login-page"><section className="auth-panel" aria-label="自部署授权"><div className="brand-name">Serenita</div>{content}</section></main>;
  if (terminal) return shell(<>
    <h1 className="device-authorization-title">{done === "approved" ? "授权成功" : terminal === "denied" ? "已取消授权" : terminal === "expired" ? "授权请求已过期" : "此授权请求已完成"}</h1>
    <p className="content-description">{done ? "请返回自部署标签页。" : "此页面的操作已结束，请返回自部署页面查看连接状态。"}</p>
    <button className="control" type="button" onClick={returnToWorkspace}>返回自部署</button>
  </>);
  if (!status) return shell(<><p role="status">{readError ? "无法确认授权请求状态" : "正在检查授权请求…"}</p>{retry}</>);

  if (accountId && route.split("?")[0] === DEVICE_AUTH_PATH) return shell(<>
    <h1 className="device-authorization-title">是否使用当前账号授权？</h1>
    <div className="device-authorization-account"><UserIcon /><div><strong>{accountName || account}</strong><span>{account}</span></div></div>
    <p className="content-description">授权后，自部署工作区可使用此账号的免费模型。自部署与在线的健康资料、会话和附件分别保存。</p>
    <div className="device-authorization-actions" aria-busy={busy}>
      <button className="control control--primary" type="button" disabled={busy || Boolean(readError)} onClick={() => void complete(() => request("/serenita/device/decision", { method: "POST", body: JSON.stringify({ user_code: code, approve: true }) }), "approved").catch(() => {})}>{busy ? <LoadingIcon className="serenita-authorization-spinner" /> : null}<span>使用当前账号</span></button>
      <button className="control" type="button" disabled={busy || Boolean(readError)} onClick={() => { onNavigate(deviceLoginPath(SIGN_IN_PATH, code)); void refresh(); }}>使用其他账号登录</button>
      <button className="control" type="button" disabled={busy || Boolean(readError)} onClick={() => void complete(() => request("/serenita/device/decision", { method: "POST", body: JSON.stringify({ user_code: code, approve: false }) }), "denied").catch(() => {})}>取消</button>
    </div>
    {error ? <p className="content-description" role="alert">{error}</p> : null}{retry}
  </>);

  return <AuthPage
    disabled={busy || Boolean(readError)}
    mode={route.split("?")[0] === SIGN_UP_PATH ? "sign_up" : "sign_in"}
    onModeChange={path => onNavigate(deviceLoginPath(path === SIGN_UP_PATH ? SIGN_UP_PATH : SIGN_IN_PATH, code))}
    onSignIn={(account, password) => complete(() => onSignIn(account, password), "approved")}
    onSignUp={(account, accountName, password, confirmPassword) => complete(() => onSignUp(account, accountName, password, confirmPassword), "approved")}
    footer={<>{retry}{accountId ? <button className="control" type="button" disabled={busy} onClick={() => onNavigate(deviceAuthorizationPath(code))}>返回授权选择</button> : null}</>}
  />;
}
