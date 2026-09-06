import { request } from "./request";

export type LabDictionaryItemUsage = {
  category_name: string;
  is_primary: number;
  result_count: number;
  report_count: number;
};

export type LabDictionaryItem = {
  item_id: string;
  item_name_zh: string;
  aliases: string[];
  description?: string | null;
  primary_category_name: string;
  related_category_names: string[];
  usage_by_category: LabDictionaryItemUsage[];
  result_count: number;
  report_count: number;
};

export type LabDictionaryCategory = {
  category_name: string;
  description?: string | null;
  item_count: number;
  primary_item_count: number;
  related_item_count: number;
  result_count: number;
  report_count: number;
};

export type LabDictionaryResponse = {
  dictionary_revision: string;
  summary: {
    item_count: number;
    category_count: number;
    relation_count: number;
  };
  items: LabDictionaryItem[];
  categories: LabDictionaryCategory[];
  relations: Array<{ item_id: string; category_name: string; is_primary: number }>;
};

export type LabDictionaryMutationResponse = {
  dictionary: LabDictionaryResponse;
  effects: Record<string, string | number | string[]>;
};

const REPORT_MUTATION_COUNT_KEYS = [
  "affected_report_count",
  "updated_report_count",
  "deleted_report_count",
  "created_report_count",
  "reclassified_result_count"
] as const;

export function labDictionaryMutationAffectsReports(
  effects: LabDictionaryMutationResponse["effects"]
) {
  return REPORT_MUTATION_COUNT_KEYS.some((key) => Number(effects[key] ?? 0) > 0);
}

export type LabItemWriteInput = {
  item_name_zh: string;
  aliases: string[];
  description: string | null;
  primary_category_name: string;
  related_category_names: string[];
  expected_dictionary_revision: string;
};

export type LabCategoryWriteInput = {
  category_name: string;
  description: string | null;
  expected_dictionary_revision: string;
};

export function fetchLabDictionary() {
  return request<LabDictionaryResponse>("/account-settings/lab-dictionary");
}

export function createLabDictionaryItem(input: LabItemWriteInput) {
  return request<LabDictionaryMutationResponse>("/account-settings/lab-dictionary/items", {
    method: "POST",
    body: JSON.stringify(input)
  });
}

export function updateLabDictionaryItem(itemId: string, input: LabItemWriteInput) {
  return request<LabDictionaryMutationResponse>(
    `/account-settings/lab-dictionary/items/${encodeURIComponent(itemId)}`,
    { method: "PATCH", body: JSON.stringify(input) }
  );
}

export function mergeLabDictionaryItems(
  sourceItemId: string,
  targetItemId: string,
  expectedDictionaryRevision: string
) {
  return request<LabDictionaryMutationResponse>(
    `/account-settings/lab-dictionary/items/${encodeURIComponent(sourceItemId)}/merge`,
    {
      method: "POST",
      body: JSON.stringify({
        target_item_id: targetItemId,
        expected_dictionary_revision: expectedDictionaryRevision
      })
    }
  );
}

export function deleteLabDictionaryItem(
  itemId: string,
  expectedDictionaryRevision: string
) {
  return request<LabDictionaryMutationResponse>(
    `/account-settings/lab-dictionary/items/${encodeURIComponent(itemId)}`,
    {
      method: "DELETE",
      body: JSON.stringify({
        expected_dictionary_revision: expectedDictionaryRevision
      })
    }
  );
}

export function createLabDictionaryCategory(input: LabCategoryWriteInput) {
  return request<LabDictionaryMutationResponse>("/account-settings/lab-dictionary/categories", {
    method: "POST",
    body: JSON.stringify(input)
  });
}

export function updateLabDictionaryCategory(
  currentCategoryName: string,
  input: LabCategoryWriteInput
) {
  return request<LabDictionaryMutationResponse>(
    `/account-settings/lab-dictionary/categories/${encodeURIComponent(currentCategoryName)}`,
    { method: "PATCH", body: JSON.stringify(input) }
  );
}

export function deleteLabDictionaryCategory(
  categoryName: string,
  expectedDictionaryRevision: string
) {
  return request<LabDictionaryMutationResponse>(
    `/account-settings/lab-dictionary/categories/${encodeURIComponent(categoryName)}`,
    {
      method: "DELETE",
      body: JSON.stringify({
        expected_dictionary_revision: expectedDictionaryRevision
      })
    }
  );
}

export function fetchMemberLabDictionary(memberId: string) {
  return request<LabDictionaryResponse>(`/members/${encodeURIComponent(memberId)}/lab-dictionary`);
}
