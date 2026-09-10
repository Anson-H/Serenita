import assert from "node:assert/strict";
import test from "node:test";
import { loadModule } from "./helpers/load-module.mjs";

const { relatedResourcesForTurn, relatedResourcePath } = loadModule("features/conversations/relatedResources.ts");
const ref = (member = "member", type = "medical_log") => ({ resource_type: type, resource_id: "same-id", member_id: member,
  name: "当日记录", created_at: "2026-09-10T00:00:00Z", updated_at: "2026-09-10T00:00:00Z" });
const result = (reference, change, turn = "turn") => ({ kind: "tool", turn_id: turn, result: { effects: {
  [change === "deleted" ? "affected_resource_refs" : "resource_refs"]: [reference],
  ...(change === "created" ? { created_entities: [{ entity_type: reference.resource_type, entity_id: reference.resource_id }] }
    : change ? { changed_entities: [{ entity_type: reference.resource_type, entity_id: reference.resource_id, change }] } : {}),
} } });

test("related resources merge completed operations by member, type and id within one turn", () => {
  const initial = ref();
  const changed = { ...initial, name: "更新后的记录", updated_at: "2026-09-11T00:00:00Z" };
  const records = [result(initial, "created"), result(changed, "modified"), result(changed),
    result(ref("other-member"), "modified"), result(ref("member", "medication")),
    result({ ...initial, resource_id: "other-turn" }, "created", "other-turn"),
    { kind: "tool", turn_id: "turn", result: { error: "保存失败" } }];
  const items = relatedResourcesForTurn(records, "turn");
  assert.equal(items.length, 3);
  assert.equal(items[0].relationship, "created");
  assert.equal(items[0].name, changed.name);
  assert.equal(items[0].updated_at, changed.updated_at);
  records.push(result(changed, "deleted"));
  assert.equal(relatedResourcesForTurn(records, "turn")[0].relationship, "deleted");
  // Results still have the same meaning when reconstructed from persisted JSON.
  assert.deepEqual(relatedResourcesForTurn(JSON.parse(JSON.stringify(records)), "turn"), relatedResourcesForTurn(records, "turn"));
});

test("references require navigation identity and encode path segments", () => {
  const invalid = [{ ...ref(), resource_type: "toString" }, { ...ref(), resource_type: "medication_batch" },
    { ...ref(), resource_type: "body_record" }, { ...ref(), updated_at: null }];
  assert.deepEqual(relatedResourcesForTurn(invalid.map(item => result(item)), "turn"), []);
  assert.equal(relatedResourcePath({ ...ref("member name"), resource_id: "record#1" }), "/health/member%20name/medical-logs/record%231");
  assert.equal(relatedResourcePath({ ...ref(), resource_type: "medication_batch", medication_id: "drug#1" }), "/health/member/medications/catalog/drug%231/batches/same-id");
});
