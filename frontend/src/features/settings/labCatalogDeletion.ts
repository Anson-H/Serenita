import type { LabDictionaryMutationResponse, LabDictionaryResponse } from "../../api/labDictionaryApi";
import type { LabCatalog } from "./settingsTypes";

type DeletionClient = {
  deleteLabDictionaryItem: (id: string, revision: string) => Promise<LabDictionaryMutationResponse>;
  deleteLabDictionaryCategory: (id: string, revision: string) => Promise<LabDictionaryMutationResponse>;
  fetchLabDictionary: () => Promise<LabDictionaryResponse>;
};

export type CatalogDeletionFailure = { id: string; name: string; reason: string; skipped: boolean };

export async function deleteLabCatalogEntries({
  catalog, ids, dictionary: initialDictionary, client, onDeleted
}: {
  catalog: LabCatalog;
  ids: string[];
  dictionary: LabDictionaryResponse;
  client: DeletionClient;
  onDeleted: (response: LabDictionaryMutationResponse) => void;
}) {
  let dictionary = initialDictionary;
  const deletedIds: string[] = [];
  const failures: CatalogDeletionFailure[] = [];
  const targets = [...new Set(ids)];
  const names = new Map(catalog === "items"
    ? dictionary.items.map((item) => [item.item_id, item.item_name_zh])
    : dictionary.categories.map((category) => [category.category_name, category.category_name]));

  for (const [index, id] of targets.entries()) {
    const name = names.get(id) ?? id;
    const category = dictionary.categories.find((entry) => entry.category_name === id);
    const exists = catalog === "items" ? dictionary.items.some((entry) => entry.item_id === id) : Boolean(category);
    if (!exists) {
      failures.push({ id, name, reason: "记录已不存在，请刷新目录。", skipped: false });
      continue;
    }
    if (catalog === "categories" && category!.primary_item_count > 0) {
      failures.push({ id, name, reason: `仍是 ${category!.primary_item_count} 个指标的主分类，请先更换这些指标的主分类。`, skipped: true });
      continue;
    }
    try {
      const response = catalog === "items"
        ? await client.deleteLabDictionaryItem(id, dictionary.dictionary_revision)
        : await client.deleteLabDictionaryCategory(id, dictionary.dictionary_revision);
      dictionary = response.dictionary;
      deletedIds.push(id);
      onDeleted(response);
    } catch (error) {
      const detail = (error as { detail?: { code?: string } } | null)?.detail;
      failures.push({
        id, name,
        reason: error instanceof Error ? error.message : "删除失败，请重试。",
        skipped: catalog === "categories" && detail?.code === "LAB_DICTIONARY_PRIMARY_CATEGORY_IN_USE"
      });
      // Read current state for the remaining explicit targets; never retry or replace a failed target.
      try {
        dictionary = await client.fetchLabDictionary();
      } catch {
        for (const remainingId of targets.slice(index + 1)) {
          failures.push({ id: remainingId, name: names.get(remainingId) ?? remainingId, reason: "无法读取最新目录，尚未删除。", skipped: false });
        }
        break;
      }
    }
  }
  return { dictionary, deletedIds, failures };
}

export function catalogDeletionMessage(catalog: LabCatalog, deletedCount: number, failures: CatalogDeletionFailure[]) {
  const noun = catalog === "items" ? "指标" : "分类";
  const skipped = failures.filter((failure) => failure.skipped);
  const errors = failures.filter((failure) => !failure.skipped);
  const parts = [`已删除 ${deletedCount} ${catalog === "items" ? "条" : "个"}${noun}。`];
  if (skipped.length) parts.push(`跳过 ${skipped.length} 个分类：仍被用作指标主分类，请先更换相关指标的主分类。`);
  if (errors.length) {
    parts.push(`${errors.length} 项未完成。${errors.slice(0, 3).map(({ name, reason }) => `${name}：${reason}`).join(" ")}`);
    if (errors.length > 3) parts.push("其余未完成项已保留选择，可稍后重试。");
  }
  return parts.join(" ");
}
