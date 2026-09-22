import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { request } from "../api/transport/request";
import { EmptyState } from "../components/EmptyState";
import { RegenerateIcon } from "../components/icons";

type Deployment = { mode: "official" | "self_hosted" };
const Context = createContext<Deployment | null>(null);

export function DeploymentProvider({ children }: { children: ReactNode }) {
  const [deployment, setDeployment] = useState<Deployment | null>(null);
  const [error, setError] = useState("");
  const [version, setVersion] = useState(0);
  useEffect(() => {
    let active = true;
    setError("");
    void request<Deployment>("/deployment").then(value => {
      if (!["official", "self_hosted"].includes(value.mode)) throw new Error("部署信息无效。");
      if (active) setDeployment(value);
    }).catch(cause => { if (active) setError(cause instanceof Error ? cause.message : "部署信息读取失败。"); });
    return () => { active = false; };
  }, [version]);
  return deployment ? <Context.Provider value={deployment}>{children}</Context.Provider> : <main className="login-page"><section className="auth-panel">
    <EmptyState layout="inline" title={error || "正在打开 Serenita…"} />
    {error ? <button type="button" className="control" onClick={() => setVersion(value => value + 1)}><RegenerateIcon /><span>重试</span></button> : null}
  </section></main>;
}

export function useDeployment() {
  const value = useContext(Context);
  if (!value) throw new Error("部署信息尚未读取。");
  return value;
}
