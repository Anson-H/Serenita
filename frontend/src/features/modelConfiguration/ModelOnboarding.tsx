import { useEffect, useState } from "react";
import { chooseModels, connectionStatus } from "../../api/models/modelServiceApi";
import { ContentDialog } from "../../components/ContentDialog";
import { ChevronRightIcon, ServerIcon, UserIcon } from "../../components/icons";
import { SerenitaProviderPanel } from "../settings/models/SerenitaProviderPanel";

export function ModelOnboarding({ onSettings }: { onSettings: () => void }) {
  const [open, setOpen] = useState(false);
  const [free, setFree] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => { let active = true; void connectionStatus().then(value => { if (active) setOpen(value.needs_onboarding); }).catch(() => { }); return () => { active = false; }; }, []);
  async function choose(choice: "own_api" | "later") {
    setBusy(true); setError("");
    try { await chooseModels(choice); setOpen(false); if (choice === "own_api") onSettings(); }
    catch (cause) { setError(cause instanceof Error ? cause.message : "配置未保存。"); }
    finally { setBusy(false); }
  }
  if (!open) return null;
  return <ContentDialog title="开始使用 Serenita" onClose={() => void choose("later")} onBack={free ? () => setFree(false) : undefined} busy={busy} bodyClassName="settings-section" actions={
    <button className="control control--compact" type="button" disabled={busy} onClick={() => void choose("later")}><ChevronRightIcon /><span>稍后配置</span></button>
  }>
    {free ? <SerenitaProviderPanel onConnected={() => setOpen(false)} /> : <>
      <p className="content-description">先选择模型服务，开始会话和资料解读。</p>
      <div className="serenita-onboarding-choices"><button className="control control--primary" type="button" disabled={busy} onClick={() => setFree(true)}><UserIcon /><span>使用 Serenita 免费模型</span></button>
        <button className="control" type="button" disabled={busy} onClick={() => void choose("own_api")}><ServerIcon /><span>使用自己的 API</span></button></div>
    </>}
    {error ? <p className="content-description" role="alert">{error}</p> : null}
  </ContentDialog>;
}
