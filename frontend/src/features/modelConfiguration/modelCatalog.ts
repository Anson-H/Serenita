import { apiClient, type AddedModel, type ModelDefaults } from '../../api/client';

export type ModelCatalog = {
  models: AddedModel[];
  defaults: ModelDefaults;
  status: 'loading' | 'ready' | 'error';
  error: string;
};
export function emptyModelCatalog(): ModelCatalog {
  return { models: [], defaults: { chat: null, title: null, compact: null, vision_parse: null, text_embedding: null, multimodal_embedding: null }, status: 'loading', error: '' };
}
export async function fetchModelCatalog(): Promise<ModelCatalog> {
  const [models, defaults] = await Promise.all([apiClient.fetchModels(), apiClient.fetchModelDefaults()]);
  return { models: models.models, defaults: defaults.defaults, status: 'ready', error: '' };
}
