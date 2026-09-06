import {
  type LabDictionaryCategory,
  type LabDictionaryItem
} from "../../api/client";
import type { LabCatalog } from "./settingsTypes";

export type DictionaryTab = LabCatalog;

export type LabDictionaryDetailPage = "root" | "primary-category" | "related-categories";

export type PendingMergeConfirmation = {
  kind: "merge-item";
  sourceItemId: string;
  targetItemId: string;
  sourceItemNameZh: string;
  targetItemNameZh: string;
  sourceResultCount: number;
  targetResultCount: number;
  run: () => Promise<void>;
};

export type CreateDialogState = {
  kind: "item" | "category";
  name: string;
  primaryCategoryName: string;
};

export type ItemDraft = {
  item_name_zh: string;
  aliases: string[];
  description: string;
  primary_category_name: string;
  related_category_names: string[];
};

export type ItemAutoSaveJob = {
  draft: ItemDraft;
  baseDraftSignature: string | null;
  targetKey: string;
  selectionEpoch: number;
};

export type CategoryDraft = {
  category_name: string;
  description: string;
};

export type CategoryAutoSaveJob = {
  draft: CategoryDraft;
  targetKey: string;
  selectionEpoch: number;
};

const emptyItemDraft: ItemDraft = {
  item_name_zh: "",
  aliases: [],
  description: "",
  primary_category_name: "",
  related_category_names: []
};

const emptyCategoryDraft: CategoryDraft = {
  category_name: "",
  description: ""
};

export function itemDraft(item?: LabDictionaryItem): ItemDraft {
  return item
    ? {
      item_name_zh: item.item_name_zh,
      aliases: [...item.aliases],
      description: item.description ?? "",
      primary_category_name: item.primary_category_name,
      related_category_names: [...item.related_category_names]
    }
    : { ...emptyItemDraft, aliases: [], related_category_names: [] };
}

export function cloneItemDraft(draft: ItemDraft): ItemDraft {
  return {
    ...draft,
    aliases: [...draft.aliases],
    related_category_names: [...draft.related_category_names]
  };
}

export function itemDraftSignature(draft: ItemDraft) {
  return JSON.stringify(draft);
}

export function categoryDraft(category?: LabDictionaryCategory): CategoryDraft {
  return category
    ? {
      category_name: category.category_name,
      description: category.description ?? ""
    }
    : { ...emptyCategoryDraft };
}

export function categoryDraftSignature(draft: CategoryDraft) {
  return JSON.stringify(draft);
}
