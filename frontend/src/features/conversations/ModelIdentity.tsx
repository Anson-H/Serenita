export function ModelIdentity({ modelId }: { modelId?: string | null }) {
  return (
    <div className="conversation-model-identity" aria-label="模型标识">
      {modelId ? `模型：${modelId}` : "模型未记录"}
    </div>
  );
}
