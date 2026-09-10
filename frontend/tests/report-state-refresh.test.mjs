import assert from "node:assert/strict";
import test from "node:test";
import { loadModule } from "./helpers/load-module.mjs";
const { ReportStateRefresher } = loadModule("features/reports/model/conversationRefresh.ts");
const { reportReferenceStatus, reportResourceKey, reportResourceStateMap } = loadModule("features/reports/reportContext.ts");
const state = (member, id, availability = "available") => ({ member_id: member, resource_id: id, resource_type: "report", availability, current_created_at: "created", current_updated_at: "new" });
const pending = () => { let resolve, reject; const promise = new Promise((yes, no) => { resolve = yes; reject = no; }); return { promise, resolve, reject }; };

function fixture() {
  let detail = { session_id: "s", member_id: "m", records: [{ content: "streaming text" }], resource_states: [state("m", "a"), state("m", "b"), state("other", "a")] };
  let active = true;
  let errors = 0;
  const requests = [];
  const refresher = new ReportStateRefresher(() => { const p = pending(); requests.push(p); return p.promise; });
  return {
    refresher, requests,
    detail: () => detail, errors: () => errors,
    leave: () => { active = false; },
    text: value => { detail = { ...detail, records: [{ content: value }] }; },
    refresh: ids => refresher.refresh({ sessionId: "s", memberId: "m", reportIds: ids, isCurrent: () => active, update: fn => { detail = fn(detail); }, onError: () => errors++ })
  };
}

test("report identity includes member and missing state stays unverified", () => {
  const ref = { member_id: "m", resource_id: "a", captured_created_at: "created", captured_updated_at: "old" };
  const map = reportResourceStateMap([state("other", "a"), state("m", "a")]);
  assert.equal(reportReferenceStatus(ref, map.get(reportResourceKey(ref))), "modified");
  assert.equal(reportReferenceStatus(ref, state("other", "a")), "unknown");
  assert.equal(reportReferenceStatus(ref), "unknown");
});

test("overlapping refreshes preserve streamed text, other members and all pending changes", async () => {
  const h = fixture();
  const first = h.refresh(["a"]);
  const second = h.refresh(["b"]);
  h.text("newly streamed text");
  h.requests[1].resolve({ session_id: "s", resource_states: [state("m", "a", "deleted"), state("m", "b", "forbidden")] });
  await second;
  h.requests[0].resolve({ session_id: "s", resource_states: [state("m", "a")] });
  await first;
  assert.equal(h.detail().records[0].content, "newly streamed text");
  assert.equal(h.detail().resource_states.find(s => s.member_id === "other").availability, "available");
  assert.deepEqual(Array.from(h.detail().resource_states.filter(s => s.member_id === "m"), s => s.availability), ["deleted", "forbidden"]);
});

test("failed refresh can retry while missing, and late results cannot update another scope", async () => {
  const h = fixture();
  const failed = h.refresh(["a"]);
  h.requests[0].reject(new Error("offline"));
  await failed;
  assert.equal(h.errors(), 1);
  const retry = h.refresh(["a"]);
  h.requests[1].resolve({ session_id: "s", resource_states: [state("m", "a")] });
  await retry;
  assert.ok(h.detail().resource_states.some(s => s.member_id === "m" && s.resource_id === "a"));
  const late = h.refresh(["a"]);
  h.leave();
  const prior = h.detail();
  h.requests[2].resolve({ session_id: "s", resource_states: [state("m", "a", "deleted")] });
  await late;
  assert.equal(h.detail(), prior);
});
