import { ApiRequestError } from "../../../api/transport/request";

/** Only a catalog revision conflict permits refreshing and rebasing a draft. */
export function isLabDictionaryRevisionConflict(error: unknown): boolean {
  return error instanceof ApiRequestError && error.detail?.code === "LAB_DICTIONARY_REVISION_CONFLICT";
}
