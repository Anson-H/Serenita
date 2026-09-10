import type { ReactNode } from "react";
import { GroupedList } from "../../components/GroupedList";
import { remoteModelIdentity } from "./remoteModelPresentation";

export function ModelIdentitySection({ remoteModelId, supplierFallbackName, children }: {
  remoteModelId: string;
  supplierFallbackName: string;
  children: ReactNode;
}) {
  const identity = remoteModelIdentity(remoteModelId);
  return <div className="model-settings-block model-identity-block">
    <GroupedList layout="fields" className="model-source-summary" density="standard">
      <div className="field-row"><span>模型 ID</span><span title={remoteModelId}>{remoteModelId}</span></div>
      <div className="field-row"><span>供应商</span><span>{identity.supplier || supplierFallbackName}</span></div>
      <div className="field-row"><span>模型</span><span title={identity.model}>{identity.model}</span></div>
      {children}
    </GroupedList>
  </div>;
}
