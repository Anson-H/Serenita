import type { AddedModel } from "../../api/client";

export function mergeModelsWithChatDefault(
  models: AddedModel[],
  chatDefault: AddedModel | null
) {
  if (!chatDefault) {
    return models;
  }
  return [
    chatDefault,
    ...models.filter((model) => model.model_id !== chatDefault.model_id)
  ];
}
