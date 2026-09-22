import type { AddedModel, ModelServiceStatus as Status } from "../../../api/models/modelTypes";
import { CheckIcon, XIcon, InfoIcon } from "../../../components/icons";
export const modelServiceStatusLabels: Record<Status, string> = {
  available: "可用", offline: "已下线", unconfigured: "服务端待配置", disconnected: "未授权", unreachable: "状态获取失败", access_denied: "无使用权限"
};
export function modelDisplayName(model: { provider_id?: string; remote_model_id: string; model_name: string }) {
  return model.provider_id === "serenita" ? model.model_name : model.remote_model_id;
}
export function ModelServiceStatus({ model }: { model: AddedModel }) {
  if (!model.service_status) return null;
  const status = model.service_status;
  const label = modelServiceStatusLabels[status];
  return <span className="model-service-status" role="status" aria-label={`${model.model_name}：${label}`} title={label}>
    <span className={`model-service-status-icon ${status === "available" ? "success" : "unconfigured"}`}>
      {status === "available" ? <CheckIcon /> : status === "unreachable" ? <InfoIcon /> : <XIcon />}
    </span>{status !== "available" ? <span className="control-row-description">{label}</span> : null}
  </span>;
}
