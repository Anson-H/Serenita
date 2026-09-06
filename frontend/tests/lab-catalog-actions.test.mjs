import assert from "node:assert/strict";
import test from "node:test";
import { loadModule } from "./helpers/load-module.mjs";

const { deleteLabCatalogEntries, catalogDeletionMessage } = loadModule("features/settings/labCatalogDeletion.ts");

function dictionary(revision = "r1") {
  return {
    dictionary_revision: revision,
    categories: [
      { category_name: "在用", primary_item_count: 1 },
      { category_name: "空分类甲", primary_item_count: 0 },
      { category_name: "空分类乙", primary_item_count: 0 }
    ],
    items: [{ item_id: "i1", item_name_zh: "指标甲", report_count: 3 }, { item_id: "i2", item_name_zh: "指标乙", report_count: 0 }],
    relations: []
  };
}

function mockClient(initial) {
  let current = structuredClone(initial);
  const calls = [];
  const remove = (catalog, key) => async (id, revision) => {
    calls.push([catalog, id, revision]);
    assert.equal(revision, current.dictionary_revision);
    current = {
      ...current,
      [catalog]: current[catalog].filter((entry) => entry[key] !== id),
      dictionary_revision: `r${Number(current.dictionary_revision.slice(1)) + 1}`
    };
    return { dictionary: current, effects: { affected_report_count: catalog === "items" ? 1 : 0 } };
  };
  return {
    calls,
    deleteLabDictionaryCategory: remove("categories", "category_name"),
    deleteLabDictionaryItem: remove("items", "item_id"),
    fetchLabDictionary: async () => current
  };
}

test("category deletion skips protected entries and serializes allowed deletions with fresh revisions", async () => {
  const initial = dictionary();
  const client = mockClient(initial);
  const updates = [];
  const result = await deleteLabCatalogEntries({ catalog: "categories", ids: ["在用", "空分类甲", "空分类乙"], dictionary: initial, client, onDeleted: (response) => updates.push(response) });
  assert.deepEqual(client.calls, [["categories", "空分类甲", "r1"], ["categories", "空分类乙", "r2"]]);
  assert.deepEqual(result.deletedIds, ["空分类甲", "空分类乙"]);
  assert.equal(result.failures[0].id, "在用");
  assert.equal(result.failures[0].skipped, true);
  assert.match(result.failures[0].reason, /主分类/);
  assert.equal(updates.length, 2);
  assert.equal(result.dictionary.dictionary_revision, "r3");
  assert.match(catalogDeletionMessage("categories", 2, result.failures), /已删除 2 个分类。 跳过 1 个分类/);
});

test("all-protected selection issues no deletion request and explains why nothing was deleted", async () => {
  const initial = dictionary();
  const client = mockClient(initial);
  const result = await deleteLabCatalogEntries({ catalog: "categories", ids: ["在用"], dictionary: initial, client, onDeleted() {} });
  assert.equal(client.calls.length, 0);
  assert.match(catalogDeletionMessage("categories", 0, result.failures), /已删除 0 个分类。 跳过 1 个分类.*更换/);
});

test("item deletion deduplicates exact targets and reports report-affecting responses", async () => {
  const initial = dictionary();
  const client = mockClient(initial);
  const effects = [];
  const result = await deleteLabCatalogEntries({ catalog: "items", ids: ["i1", "i1", "i2"], dictionary: initial, client, onDeleted: (response) => effects.push(response.effects) });
  assert.deepEqual(client.calls, [["items", "i1", "r1"], ["items", "i2", "r2"]]);
  assert.deepEqual(result.dictionary.items, []);
  assert.equal(result.failures.length, 0);
  assert.equal(effects.length, 2);
});

test("one failed delete is not retried and does not prevent a remaining valid target", async () => {
  const initial = dictionary();
  const refreshed = dictionary("r7");
  const client = mockClient(refreshed);
  const remove = client.deleteLabDictionaryItem;
  const attempts = [];
  client.deleteLabDictionaryItem = async (id, revision) => {
    attempts.push(id);
    if (id === "i1") throw new Error("目录已变化，请刷新。");
    return remove(id, revision);
  };
  const result = await deleteLabCatalogEntries({ catalog: "items", ids: ["i1", "i2"], dictionary: initial, client, onDeleted() {} });
  assert.deepEqual(attempts, ["i1", "i2"]);
  assert.deepEqual(client.calls, [["items", "i2", "r7"]]);
  assert.deepEqual(result.deletedIds, ["i2"]);
  assert.equal(result.failures[0].id, "i1");
  assert.equal(result.failures[0].skipped, false);
  assert.match(catalogDeletionMessage("items", 1, result.failures), /指标甲：目录已变化/);
});

test("loss of current directory stops remaining deletions without claiming success", async () => {
  const initial = dictionary();
  const attempts = [];
  const client = {
    deleteLabDictionaryItem: async (id) => { attempts.push(id); throw new Error("网络中断"); },
    fetchLabDictionary: async () => { throw new Error("网络中断"); }
  };
  const result = await deleteLabCatalogEntries({ catalog: "items", ids: ["i1", "i2"], dictionary: initial, client, onDeleted() {} });
  assert.deepEqual(attempts, ["i1"]);
  assert.equal(result.deletedIds.length, 0);
  assert.deepEqual(result.failures.map(({ id }) => id), ["i1", "i2"]);
  assert.match(result.failures[1].reason, /尚未删除/);
});

test("server-reported primary-category protection is counted as skipped", async () => {
  const initial = dictionary();
  const client = mockClient(initial);
  client.deleteLabDictionaryCategory = async () => {
    throw Object.assign(new Error("分类刚被设为主分类"), { detail: { code: "LAB_DICTIONARY_PRIMARY_CATEGORY_IN_USE" } });
  };
  const result = await deleteLabCatalogEntries({ catalog: "categories", ids: ["空分类甲"], dictionary: initial, client, onDeleted() {} });
  assert.equal(result.failures[0].skipped, true);
  assert.match(catalogDeletionMessage("categories", 0, result.failures), /跳过 1 个分类/);
});

test("missing targets are never replaced with another available entry", async () => {
  const initial = dictionary();
  const client = mockClient(initial);
  const result = await deleteLabCatalogEntries({ catalog: "items", ids: ["removed"], dictionary: initial, client, onDeleted() {} });
  assert.equal(client.calls.length, 0);
  assert.equal(result.failures[0].id, "removed");
  assert.match(result.failures[0].reason, /不存在/);
});

test("each category is rechecked against the last returned directory", async () => {
  const initial = dictionary();
  const client = mockClient(initial);
  const remove = client.deleteLabDictionaryCategory;
  client.deleteLabDictionaryCategory = async (...args) => {
    const response = await remove(...args);
    response.dictionary.categories.find((entry) => entry.category_name === "空分类乙").primary_item_count = 1;
    return response;
  };
  const result = await deleteLabCatalogEntries({ catalog: "categories", ids: ["空分类甲", "空分类乙"], dictionary: initial, client, onDeleted() {} });
  assert.equal(client.calls.length, 1);
  assert.equal(result.failures[0].id, "空分类乙");
  assert.equal(result.failures[0].skipped, true);
});
