import assert from "node:assert/strict";
import test from "node:test";
import { loadModule } from "./helpers/load-module.mjs";

const deferred = () => {
  let resolve, reject;
  const promise = new Promise((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
};
const settle = () => new Promise(resolve => setImmediate(resolve));
const ref = current => ({ current });
const noop = () => {};

test("conversation refresh cannot overwrite a newer title, refresh or expired page", async () => {
  const { createConversationIndex } = loadModule("features/conversations/conversationIndex.ts");
  const reads = [];
  let current = true;
  let sessions = [{ session_id: "a", title: "initial" }];
  const index = createConversationIndex(() => {
    const result = deferred(); reads.push(result); return result.promise;
  }, next => { sessions = typeof next === "function" ? next(sessions) : next; }, () => current);
  const pending = index.refresh();
  index.update(items => items.map(item => ({ ...item, title: "renamed" })));
  reads[0].resolve({ sessions: [{ session_id: "a", title: "old title" }] });
  await pending;
  assert.equal(sessions[0].title, "renamed");
  const first = index.refresh(), second = index.refresh();
  assert.equal(reads.length, 2, "overlapping refreshes share one request");
  reads[1].resolve({ sessions: [{ session_id: "a", title: "latest" }] });
  await Promise.all([first, second]);
  assert.equal(sessions[0].title, "latest");
  let relevant = true;
  const leaving = index.refresh(() => relevant);
  relevant = false; reads[2].resolve({ sessions: [] }); await leaving;
  assert.equal(sessions.length, 1);
  const logout = index.refresh(); current = false;
  reads[3].resolve({ sessions: [] }); await logout;
  index.update([]);
  assert.equal(sessions.length, 1);
});

test("refreshes after a mutation share a fresh read once the stale request finishes", async () => {
  const { createConversationIndex } = loadModule("features/conversations/conversationIndex.ts");
  const reads = [];
  let sessions = [];
  const index = createConversationIndex(() => {
    const result = deferred(); reads.push(result); return result.promise;
  }, next => { sessions = typeof next === "function" ? next(sessions) : next; }, () => true);
  const old = index.refresh();
  index.update([{ session_id: "new", title: "submitted" }]);
  const refreshes = Array.from({ length: 8 }, () => index.refresh());
  assert.equal(reads.length, 1);
  reads[0].resolve({ sessions: [] }); await old; await settle();
  assert.equal(sessions[0].title, "submitted");
  assert.equal(reads.length, 2);
  reads[1].resolve({ sessions: [{ session_id: "new", title: "generated" }] });
  await Promise.all(refreshes);
  assert.equal(sessions[0].title, "generated");
});

function reportActions(api, extra = {}) {
  const effects = [];
  const state = {
    detailRequestSequenceRef: ref(1), isCurrentScope: () => true,
    canEdit: true, selectedReport: { report_id: "a", member_id: "member-a" },
    saving: false, labItemMutation: null, deletingAnalysis: false,
    setSaving: value => effects.push(["saving", value]),
    setActionError: value => effects.push(["error", value]), memberId: "member-a",
    selectedReportIdRef: ref("a"), setSelectedReport: value => effects.push(["detail", value]),
    refreshConversationReportStates: async ids => effects.push(["resources", ids]),
    loadReports: async () => effects.push(["list"]), setActionMessage: value => effects.push(["message", value]),
    deleting: false, setLabItemMutation: noop, analyzing: false, setDeletingAnalysis: noop,
    setLatestAnalysisReportId: noop, setAnalysisError: noop, addingSources: false,
    setAddingSources: noop, ...extra
  };
  const { createReportMutationActions } = loadModule("features/reports/reportMutationActions.ts", {}, {
    "../../api/client": { apiClient: api }
  });
  return { state, effects, actions: createReportMutationActions(state) };
}

test("a report save returning after A to B to A cannot update the new selection", async () => {
  const gate = deferred();
  const calls = [];
  const { state, effects, actions } = reportActions({ updateReportField: (...args) => {
    calls.push(args); return gate.promise;
  } });
  const save = actions.updateSelectedReportField({ field: "report_name", value: "edited" });
  state.detailRequestSequenceRef.current += 2;
  gate.resolve({ report_id: "a", report_name: "stale" });
  assert.equal(await save, false);
  assert.deepEqual(calls, [["member-a", "a", { field: "report_name", value: "edited" }]]);
  assert.deepEqual(effects, [["saving", true], ["error", ""]]);
});

test("report mutation publishes one detail, list and resource refresh and preserves original failure", async () => {
  const updated = { report_id: "a", report_name: "edited" };
  const success = reportActions({ updateReportField: async () => updated });
  assert.equal(await success.actions.updateSelectedReportField({ field: "report_name", value: "edited" }), updated);
  assert.deepEqual(success.effects.filter(([name]) => ["detail", "list", "resources"].includes(name)), [
    ["detail", updated], ["resources", ["a"]], ["list"]
  ]);
  const failure = reportActions({
    updateReportField: async () => { throw new Error("original save failure"); },
    getReport: async () => { throw new Error("readback failure"); }
  });
  assert.equal(await failure.actions.updateSelectedReportField({ field: "report_name", value: "edited" }), false);
  assert.deepEqual(failure.effects.slice(-2), [["error", "original save failure"], ["saving", false]]);
});

test("model save reads and publishes the catalog once; cancelled probes cannot republish it", async () => {
  const calls = [];
  const gate = deferred();
  const models = [{ model_id: "provider:model", model_name: "updated" }];
  const defaults = { chat: models[0] };
  const apiClient = {
    updateModel: async (...args) => calls.push(["update", ...args]),
    fetchModels: async () => { calls.push(["models"]); return { models }; },
    fetchModelDefaults: async () => { calls.push(["defaults"]); return { defaults }; },
    probeModelCapabilities: () => gate.promise
  };
  const { createModelSettingsActions } = loadModule("features/settings/modelSettingsActions.ts", {}, {
    "../../api/client": { apiClient },
    "../../components/StatusNotificationCenter": { showStatusNotification: noop }
  });
  const controllers = ref(new Map());
  const actions = createModelSettingsActions(new Proxy({
    modelProbeAbortControllersRef: controllers,
    publishModelCatalog: (...args) => calls.push(["publish", ...args])
  }, { get: (target, key) => target[key] ?? noop }));
  await actions.updateAddedModel("provider:model", { model_name: "updated" }, { notify: false });
  assert.deepEqual(calls, [
    ["update", "provider:model", { model_name: "updated" }], ["models"], ["defaults"], ["publish", models, defaults]
  ]);
  const probe = actions.probeAddedModel("provider:model");
  controllers.current.get("provider:model").abort();
  gate.resolve({}); await probe;
  assert.equal(calls.length, 4);
  assert.equal(controllers.current.size, 0);
});

function editor(onSave, onDelete = async () => true) {
  const { modelSettingsPayload, modelSettingsSignature } = loadModule("features/settings/modelSettingsDraft.ts");
  const draft = { modelName: "initial", thinkingModes: ["off"], capabilityProfiles: {}, contextWindowTokens: "1024", maxOutputTokens: "128" };
  const payload = modelSettingsPayload(draft);
  const state = {
    saveRunningRef: ref(false), saveQueueRef: ref([]), lastSavedSignatureRef: ref(modelSettingsSignature(payload)),
    lastSavedPayloadRef: ref(payload), onSaveRef: ref(onSave), mountedRef: ref(true),
    setValidationError: value => { state.error = value; }, draftRef: ref(draft), setDraft: noop,
    saveTimerRef: ref(null), deletingRef: ref(false), setDeleting: noop, onDelete, probing: false, onProbe: noop
  };
  const { createModelEditorActions } = loadModule("features/settings/modelEditorActions.ts", { window: { setTimeout, clearTimeout } });
  return { state, actions: createModelEditorActions(state) };
}

test("model queue coalesces pending drafts and deletion waits for all saved fields", async () => {
  const first = deferred(), second = deferred();
  const events = [];
  const { state, actions } = editor(patch => {
    events.push(patch); return events.length === 1 ? first.promise : second.promise;
  }, async () => { events.push("delete"); return true; });
  actions.scheduleModelDraft(draft => ({ ...draft, modelName: "first" }), { immediate: true });
  actions.scheduleModelDraft(draft => ({ ...draft, modelName: "latest" }), { immediate: true });
  actions.scheduleModelDraft(draft => ({ ...draft, maxOutputTokens: "256" }), { immediate: true });
  const deletion = actions.deleteModel();
  assert.deepEqual(events, [{ model_name: "first" }]);
  first.resolve(); await settle();
  assert.deepEqual(events, [{ model_name: "first" }, { model_name: "latest", max_output_tokens: 256 }]);
  assert.equal(state.draftRef.current.modelName, "latest");
  second.resolve(); await deletion;
  assert.equal(events.at(-1), "delete");
});

test("failed model autosave keeps the latest input and retries against the last saved baseline", async () => {
  const gate = deferred();
  const patches = [];
  const { state, actions } = editor(patch => { patches.push(patch); return patches.length === 1 ? gate.promise : Promise.resolve(); });
  actions.scheduleModelDraft(draft => ({ ...draft, modelName: "first" }), { immediate: true });
  actions.scheduleModelDraft(draft => ({ ...draft, modelName: "latest" }), { immediate: true });
  gate.reject(new Error("offline")); await settle();
  assert.equal(state.error, "offline");
  assert.equal(state.draftRef.current.modelName, "latest");
  assert.equal(state.lastSavedPayloadRef.current.model_name, "initial");
  actions.scheduleModelDraft(draft => ({ ...draft, maxOutputTokens: "256" }), { immediate: true });
  await settle();
  assert.deepEqual(patches[1], { model_name: "latest", max_output_tokens: 256 });
  assert.equal(state.error, "");
});

test("category saves follow renamed targets and latest revisions without replacing another selection", async () => {
  const gate = deferred();
  const writes = [], selected = [], forms = [];
  const dictionary = (revision, name) => ({ dictionary_revision: revision, categories: [{ category_name: name }, { category_name: "B" }], items: [], relations: [] });
  const state = {
    savedCategoryTargetsRef: ref(new Map()), dictionaryRef: ref(dictionary("r0", "A")),
    selectedIdRef: ref("A"), selectionEpochRef: ref(1), categorySaveQueueRef: ref([]),
    categoryFormRef: ref({ category_name: "A", description: "" }), setCategoryForm: value => forms.push(value),
    categorySaveTimerRef: ref(null), categorySaveRunningRef: ref(false), setSaving: noop,
    setError: noop, setDictionary: noop, setSelectedId: value => selected.push(value), onReportsChanged: noop
  };
  const { createLabCategoryEditorActions } = loadModule("features/settings/labCategoryEditorActions.ts", {}, {
    "../../api/client": { apiClient: {
      updateLabDictionaryCategory: async (target, input) => {
        writes.push([target, input]);
        if (writes.length === 1) return gate.promise;
        if (writes.length === 2) throw new Error("请刷新目录后重试");
        return { dictionary: dictionary("r3", "A1"), effects: {} };
      },
      fetchLabDictionary: async () => dictionary("r2", "A1")
    } }
  });
  const actions = createLabCategoryEditorActions(state);
  actions.scheduleCategoryDraft(draft => ({ ...draft, category_name: "A1" }), { immediate: true });
  actions.scheduleCategoryDraft(draft => ({ ...draft, description: "latest" }), { immediate: true });
  state.selectedIdRef.current = "B";
  state.selectionEpochRef.current++;
  state.categoryFormRef.current = { category_name: "B", description: "B draft" };
  const formsBefore = forms.length;
  gate.resolve({ dictionary: dictionary("r1", "A1"), effects: {} }); await settle();
  assert.deepEqual(writes.map(([target, input]) => [target, input.expected_dictionary_revision, input.description]), [
    ["A", "r0", null], ["A1", "r1", "latest"], ["A1", "r2", "latest"]
  ]);
  assert.equal(state.dictionaryRef.current.dictionary_revision, "r3");
  assert.equal(state.categoryFormRef.current.description, "B draft");
  assert.equal(forms.length, formsBefore);
  assert.deepEqual(selected, []);
});
