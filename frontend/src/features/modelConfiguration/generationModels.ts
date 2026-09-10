import type { AddedModel, GenerationModel } from "../../api/modelTypes";

export function isGenerationModel(model: AddedModel): model is GenerationModel {
  return model.model_type === "generation";
}
