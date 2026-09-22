import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { authorizeModels, connectionStatus, disconnectModels, modelConfigurationChanged, pollAuthorization, type ConnectionStatus } from "../../../api/models/modelServiceApi";
import { ContentDialog } from "../../../components/ContentDialog";
import { EmptyState } from "../../../components/EmptyState";
import { GroupedList, ReadonlyField } from "../../../components/GroupedList";
import { IdentityRowCopy } from "../../../components/IdentityRowCopy";
import { CheckIcon, InfoIcon, LoadingIcon, LogOutIcon, RegenerateIcon, UserIcon } from "../../../components/icons";

function ConnectionHelp({ onClose, onRetry }: { onClose: () => void; onRetry: () => void }) {
  return <ContentDialog title="官方服务配置说明" onClose={onClose} bodyClassName="serenita-connection-help" actions={
    <button className="control control--primary" type="button" onClick={onRetry}><RegenerateIcon /><span>重新检查配置</span></button>
  }>
    <p className="content-description">当前是自部署实例。请部署管理员在本地后端的启动环境中设置官方模型服务地址。</p>
    <GroupedList density="standard" layout="fields">
      <ReadonlyField label="部署模式" value="self_hosted" />
      <ReadonlyField label="配置项" value={<code>SERENITA_OFFICIAL_URL</code>} />
    </GroupedList>
    <p className="content-description">填写实际官方服务的 HTTPS 基础地址，不附加 /api/serenita。该地址需要提供官方授权网页及模型服务接口；本机测试允许使用 HTTP 回环地址。</p>
    <p className="content-description">保存部署配置并重启本地后端后，重新检查配置，即可使用“授权登录”。官方账号和上游 API 密钥由各自服务管理。</p>
  </ContentDialog>;
}

export function SerenitaProviderPanel({ onConnected, children }: { onConnected?: () => void; children?: ReactNode }) {
  const [state, setState] = useState<ConnectionStatus | null>(null);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [help, setHelp] = useState(false);
  const [version, setVersion] = useState(0);
  const stateRef = useRef(state);
  const mutation = useRef(0);
  const acting = useRef(false);
  const mounted = useRef(true);
  const onConnectedRef = useRef(onConnected);
  useEffect(() => { onConnectedRef.current = onConnected; }, [onConnected]);
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; mutation.current++; }; }, []);
  const save = useCallback((value: ConnectionStatus) => {
    const connectedNow = value.connected && !stateRef.current?.connected;
    stateRef.current = value; setState(value);
    if (connectedNow) { modelConfigurationChanged(); onConnectedRef.current?.(); }
  }, []);
  const showError = useCallback((cause: unknown) => setError(cause instanceof Error ? cause.message : "操作失败，请重试。"), []);

  useEffect(() => {
    let active = true;
    if (acting.current) return;
    const ticket = mutation.current;
    setLoading(true);
    void connectionStatus().then(value => {
      if (!active || ticket !== mutation.current) return;
      save(value); setError(value.connection_error ?? "");
    }).catch(cause => { if (active && ticket === mutation.current) showError(cause); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [version, save, showError]);

  useEffect(() => {
    const refresh = () => { if (!acting.current) setVersion(value => value + 1); };
    window.addEventListener("focus", refresh);
    return () => { window.removeEventListener("focus", refresh); };
  }, []);

  const applyResult = useCallback((value: ConnectionStatus) => {
    if (stateRef.current?.user_code !== value.user_code) mutation.current++;
    save(value);
    setError(value.authorization_error ?? value.connection_error ?? "");
    if (value.connected) {
      setMessage("官方账号已连接。");
    } else if (value.authorization_status === "access_denied") {
      setMessage("已取消授权。");
    } else if (value.authorization_status === "approved") {
      setMessage("授权已在其他页面确认，正在连接。");
    } else if (["expired_token", "invalid_grant"].includes(value.authorization_status ?? "")) {
      setMessage("授权请求已过期，可以重新授权。");
    }
  }, [save]);

  useEffect(() => {
    if (!state?.user_code) return;
    const code = state.user_code;
    let active = true;
    let polling = false;
    let retryAt = 0;
    const tick = async () => {
      const current = stateRef.current;
      if (!active || acting.current || polling || current?.user_code !== code) return;
      const now = Date.now();
      if (current.device_expires_at && Date.parse(current.device_expires_at) <= now) {
        mutation.current++;
        save({ ...current, user_code: null, verification_uri: null, device_expires_at: null, next_poll_at: null });
        setMessage("授权请求已过期，可以重新授权。"); setError("");
        setVersion(value => value + 1);
        return;
      }
      if (now < Math.max(retryAt, Date.parse(current.next_poll_at ?? "") || 0)) return;
      polling = true;
      const ticket = mutation.current;
      try {
        const value = await pollAuthorization(code);
        if (active && ticket === mutation.current && stateRef.current?.user_code === code) applyResult(value);
      } catch (cause) {
        if (active && ticket === mutation.current) showError(cause);
      } finally { polling = false; retryAt = Date.now() + 5000; }
    };
    const timer = window.setInterval(() => void tick(), 1000);
    void tick();
    return () => { active = false; window.clearInterval(timer); };
  }, [state?.user_code, applyResult, save, showError]);

  function reload() {
    setError(""); setMessage(""); setVersion(v => v + 1);
  }

  async function action(kind: "connect" | "disconnect") {
    if (acting.current) return;
    const current = stateRef.current;
    const authorizationTab = kind === "connect" && current?.deployment_mode === "self_hosted" ? window.open("about:blank", "_blank") : null;
    if (authorizationTab) authorizationTab.opener = null;
    acting.current = true;
    const ticket = ++mutation.current;
    setBusy(true); setMessage(""); setError("");
    try {
      if (kind === "connect") {
        const value = await authorizeModels();
        if (mounted.current && ticket === mutation.current) {
          save(value);
          if (value.user_code && value.verification_uri) {
            if (authorizationTab && !authorizationTab.closed) {
              const url = new URL(value.verification_uri);
              url.hash = new URLSearchParams({ return_to: new URL("/setting/providers/serenita", window.location.origin).href }).toString();
              authorizationTab.location.replace(url.href);
            } else if (!authorizationTab) setMessage("浏览器未打开授权页，请允许弹出窗口后再次点击授权登录。");
          } else { authorizationTab?.close(); applyResult(value); }
        } else authorizationTab?.close();
      } else if (kind === "disconnect") {
        const result = await disconnectModels();
        if (!mounted.current || ticket !== mutation.current) return;
        if (current) save({
          ...current, connected: false, account_name: null, expires_at: null,
          user_code: null, verification_uri: null, device_expires_at: null, next_poll_at: null
        });
        modelConfigurationChanged(); setVersion(v => v + 1);
        setMessage(result.remote_revoked ? "已解除此自部署实例的 Serenita 授权。" : "本地授权已清除，在线服务暂时无法确认撤销。");
      }
    } catch (cause) {
      authorizationTab?.close();
      if (mounted.current && ticket === mutation.current) showError(cause);
    } finally {
      acting.current = false;
      if (mounted.current) { setBusy(false); setLoading(false); }
    }
  }

  const official = state?.deployment_mode === "official";
  const title = state?.connected ? state.account_name || "官方账号" : state?.service_available ? "未连接官方账号" : "服务待配置";
  const description = state?.connected ? undefined : state?.service_available
    ? "授权登录后即可使用免费的生成模型和向量模型。" : "部署管理员尚未设置官方模型服务地址。";

  return <section className="settings-section serenita-provider-panel" aria-label="Serenita 免费模型">
    {state ? <div className="identity-row serenita-account-row" aria-label="官方账号状态" aria-busy={busy || loading}>
      <span className="health-member-avatar" aria-hidden="true"><UserIcon /></span>
      <IdentityRowCopy title={title} description={description} />
      <div className="serenita-account-actions">
        {state.connected ? official ? <span className="serenita-account-status"><CheckIcon /><span>已登录</span></span>
          : <button className="control control--compact" type="button" disabled={busy || loading} onClick={() => void action("disconnect")}><LogOutIcon /><span>{busy ? "正在解除授权…" : "解除授权"}</span></button>
          : !state.service_available ? <button className="control control--primary" type="button" onClick={() => setHelp(true)}><InfoIcon /><span>查看配置说明</span></button>
            : <button className="control control--primary" type="button" aria-busy={busy} disabled={busy || loading} onClick={() => void action("connect")}>{busy ? <LoadingIcon className="serenita-authorization-spinner" /> : <UserIcon />}<span>{busy ? "正在处理…" : "授权登录"}</span></button>}
      </div>
    </div> : <EmptyState layout="inline" role="status" title={loading ? "正在读取连接状态…" : "连接状态读取失败"} />}
    {error ? <p className="content-description" role="alert">{error}</p> : null}
    {message ? <p className="content-description" role="status">{message}</p> : null}
    {!state && !loading ? <button className="control" type="button" onClick={reload}><RegenerateIcon /><span>重新读取连接状态</span></button> : null}
    {state?.connected && !error ? children : null}
    {help ? <ConnectionHelp onClose={() => setHelp(false)} onRetry={() => { setHelp(false); reload(); }} /> : null}
  </section>;
}
