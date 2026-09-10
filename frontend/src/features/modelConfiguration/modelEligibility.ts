import { isGenerationModel } from "./generationModels";
import type { AddedModel, ModelDefaults } from "../../api/modelTypes";

export const modelTypeLabels = { generation: "生成模型", embedding: "向量模型", unknown: "类型未确认" };
export const modalityLabels = { text: "文本", image: "图片", audio: "音频", video: "视频", document: "文档" };
export function supportedEmbeddingModalities(model: AddedModel) {
  const caps = model.embedding_capabilities;
  const modalities = new Set<keyof typeof modalityLabels>(caps?.supports_text ? ["text"] : []);
  for (const mime of caps?.file_mime_types ?? []) {
    const prefix = mime.split("/", 1)[0];
    modalities.add(prefix === "image" || prefix === "audio" || prefix === "video" ? prefix : "document");
  }
  return (Object.keys(modalityLabels) as (keyof typeof modalityLabels)[]).filter(key => modalities.has(key));
}
export function eligibleForDefault(model: AddedModel, purpose: keyof ModelDefaults) {
  if (purpose === "text_embedding") return model.model_type === "embedding" && supportedEmbeddingModalities(model).includes("text");
  if (purpose === "multimodal_embedding") return model.model_type === "embedding" && supportedEmbeddingModalities(model).length >= 2;
  return isGenerationModel(model) && model.supports_text && (purpose !== "vision_parse" || model.file_mime_types.some(type => type.startsWith("image/")));
}
