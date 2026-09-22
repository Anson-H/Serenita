import type { AddedModel, ModelDefaults } from '../../api/models/modelTypes';

export type ModelCatalog = {
  models: AddedModel[];
  defaults: ModelDefaults;
  status: 'loading' | 'ready' | 'error';
  error: string;
};
export function emptyModelCatalog(): ModelCatalog {
  return { models: [], defaults: { chat: null, title: null, compact: null, memory_generation: null, vision_parse: null, text_embedding: null, multimodal_embedding: null }, status: 'loading', error: '' };
}
