import { useEffect, useState } from "react";
import { apiClient, type AddedModel } from "../../api/client";

const EMPTY_TYPES: string[] = [];

export function useAttachmentCapabilities(model: AddedModel | undefined, visionModel: AddedModel | null) {
  const [revision, setRevision] = useState(0);
  const [state, setState] = useState<{
    model: AddedModel | undefined; visionModel: AddedModel | null; revision: number;
    types: string[]; error: string;
  } | null>(null);
  useEffect(() => {
    let active = true;
    if (!model) return;
    void apiClient.fetchAttachmentCapabilities(model.model_id).then(result => {
      if (!active) return;
      if (result.model_id !== model.model_id || !Array.isArray(result.file_mime_types)
        || result.file_mime_types.some(type => typeof type !== "string")) {
        throw new Error("附件能力响应无效。");
      }
      setState({ model, visionModel, revision, types: result.file_mime_types, error: "" });
    }).catch(error => {
      if (active) setState({
        model, visionModel, revision, types: EMPTY_TYPES,
        error: error instanceof Error && error.message ? error.message : "附件能力获取失败。"
      });
    });
    return () => { active = false; };
  }, [model, visionModel, revision]);
  const current = state?.model === model && state?.visionModel === visionModel && state?.revision === revision;
  return {
    selectedModelFileMimeTypes: current ? state.types : EMPTY_TYPES,
    attachmentCapabilitiesReady: Boolean(current && !state.error),
    attachmentCapabilitiesError: current ? state.error : "",
    retryAttachmentCapabilities: () => setRevision(value => value + 1)
  };
}
