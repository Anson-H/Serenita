import type { LabCategoryWriteInput } from "../../../api/knowledge/labDictionaryApi";

import type { CategoryDraft } from "./labDictionaryDrafts";
export function categoryInput(draft: CategoryDraft, revision: string): LabCategoryWriteInput {
  return {
    category_name: draft.category_name.trim(),
    description: draft.description.trim() || null,
    expected_dictionary_revision: revision
  };
}

