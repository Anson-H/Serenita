import type { LabItemWriteInput, LabDictionaryResponse } from "../../../api/knowledge/labDictionaryApi";

import type { ItemAutoSaveJob, ItemDraft } from "./labDictionaryDrafts";
import { itemDraft, itemDraftSignature } from "./labDictionaryDrafts";
export function itemInput(draft: ItemDraft, revision: string): LabItemWriteInput {
  return {
    item_name_zh: draft.item_name_zh.trim(),
    aliases: draft.aliases,
    description: draft.description.trim() || null,
    primary_category_name: draft.primary_category_name,
    related_category_names: draft.related_category_names,
    expected_dictionary_revision: revision
  };
}

export function itemJobCanRebase(job: ItemAutoSaveJob, latestDictionary: LabDictionaryResponse, resolvedTarget: string) {
  const latestItem = latestDictionary.items.find(
    (item) => item.item_id === (resolvedTarget || job.targetKey)
  );
  return Boolean(
    latestItem
    && job.baseDraftSignature
    && itemDraftSignature(itemDraft(latestItem)) === job.baseDraftSignature
  );
}

