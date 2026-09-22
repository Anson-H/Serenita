import type { AddedModel, GenerationModel } from "../../api/models/modelTypes";

export function isGenerationModel(model: AddedModel): model is GenerationModel {
  return model.model_type === "generation";
}
