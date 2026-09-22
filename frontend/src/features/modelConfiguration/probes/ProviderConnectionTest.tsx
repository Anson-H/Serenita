import type { ProviderConnectionTestState } from "../../../utils/requestStatus";
import { RegenerateIcon } from "../../../components/icons";

export function ProviderConnectionTest({ state, onTest, disabled = false }: { state?: ProviderConnectionTestState; disabled?: boolean; onTest: () => void | Promise<void> }) {
  const busy = state?.status === "testing";
  return <div className="settings-section provider-connection-test">
    <button className={`control provider-detail-test-button ${state?.status ?? "idle"}`} type="button" disabled={!busy && disabled} onClick={() => void onTest()}><RegenerateIcon /><span>{busy ? "测试中" : state?.status === "success" ? "测试成功" : "测试连接"}</span></button>
    {state?.message ? <p role="status" className="content-description">{state.message}</p> : null}
  </div>;
}
