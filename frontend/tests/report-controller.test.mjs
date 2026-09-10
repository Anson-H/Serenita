import assert from 'node:assert/strict';
import test from 'node:test';
import { loadModule } from './helpers/load-module.mjs';

const noop = () => {};
const deferred = () => {
  let resolve, reject;
  const promise = new Promise((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
};
const tick = () => new Promise(resolve => setImmediate(resolve));
const report = (id, name = id) => ({ report_id: id, member_id: 'member', report_name: name, report_time: '2026-09-09T08:00:00+08:00', report_type: '检验报告', created_at: 'created', updated_at: 'updated' });
function detailFixture(options = {}) {
  const errors = [], opened = [];
  const { ReportDetailState } = loadModule('features/reports/model/detail.ts');
  const detail = new ReportDetailState('member', {
    read: async (_member, id) => report(id), isCurrent: () => true,
    beforeNavigate: async () => true, onError: error => errors.push(error),
    onOpened: id => opened.push(id), ...options,
  });
  return { detail, errors, opened };
}
function mutations(detail, api, options = {}) {
  const changed = [], errors = [];
  const { ReportMutationActions } = loadModule('features/reports/model/mutations.ts', {}, {
    '../../../api/client': { apiClient: api },
  });
  const controller = new ReportMutationActions(detail, {
    canEdit: () => true, deleting: () => false, analyzing: () => false,
    onChanged: async ids => changed.push(ids), onAnalysisDeleted: noop,
    onError: error => errors.push(error), onMessage: noop, ...options,
  });
  return { controller, changed, errors };
}

test('the latest navigation wins when two selections wait for the same save', async () => {
  const save = deferred(), reads = [];
  const { detail } = detailFixture({
    beforeNavigate: () => save.promise,
    read: async (_member, id) => { reads.push(id); return report(id); },
  });
  const runningSave = detail.capture();
  const first = detail.open('a'), last = detail.open('b');
  assert.equal(runningSave.isCurrent(), true, 'waiting to navigate must allow the current save to finish');
  assert.deepEqual(reads, []);
  save.resolve(true);
  assert.equal(await first, null);
  assert.equal((await last).report_id, 'b');
  assert.deepEqual(reads, ['b']);
  assert.equal(detail.snapshot().selectedReportId, 'b');
});

test('a late detail response cannot reopen an earlier selection', async () => {
  const reads = new Map();
  const { detail, opened } = detailFixture({ read: (_member, id) => {
    const gate = deferred(); reads.set(id, gate); return gate.promise;
  } });
  const first = detail.open('a'); await tick();
  const second = detail.open('b'); await tick();
  reads.get('b').resolve(report('b')); await second;
  reads.get('a').resolve(report('a')); assert.equal(await first, null);
  assert.deepEqual(opened, ['b']);
  assert.equal(detail.snapshot().selectedReportId, 'b');
});

test('a background read cannot overwrite a report field saved after that read began', async () => {
  const gate = deferred(); let reads = 0;
  const { detail } = detailFixture({ read: async (_member, id) => ++reads === 1 ? report(id) : gate.promise });
  await detail.open('a');
  const refresh = detail.refresh();
  const edited = report('a', 'saved');
  const { controller } = mutations(detail, { updateReportField: async () => edited });
  assert.equal(await controller.updateSelectedReportField({ field: 'report_name', value: 'saved' }), edited);
  gate.resolve(report('a', 'stale')); await refresh;
  assert.equal(detail.snapshot().selectedReport.report_name, 'saved');
});

test('field saves stay serial and expose pending state until the last write finishes', async () => {
  const { detail } = detailFixture(); await detail.open('a');
  const first = deferred(), second = deferred(), writes = [];
  const { controller, changed } = mutations(detail, { updateReportField: (_member, _id, input) => {
    writes.push(input.value); return writes.length === 1 ? first.promise : second.promise;
  } });
  const a = controller.updateSelectedReportField({ field: 'report_name', value: 'first' });
  const b = controller.updateSelectedReportField({ field: 'report_name', value: 'second' });
  await tick(); assert.deepEqual(writes, ['first']);
  first.resolve(report('a', 'first')); await a; await tick();
  assert.deepEqual(writes, ['first', 'second']);
  assert.equal(controller.snapshot().saving, true);
  second.resolve(report('a', 'second')); await b;
  assert.equal(controller.snapshot().saving, false);
  assert.equal(detail.snapshot().selectedReport.report_name, 'second');
  assert.deepEqual(changed, [['a'], ['a']]);
});

test('selection changes stop queued writes and clear operation state without publishing the running write', async () => {
  const { detail } = detailFixture(); await detail.open('a');
  const gate = deferred(), writes = [];
  const { controller, changed } = mutations(detail, { updateReportField: (_member, id) => {
    writes.push(id); return gate.promise;
  } });
  const first = controller.updateSelectedReportField({ field: 'report_name', value: 'first' });
  const queued = controller.updateSelectedReportField({ field: 'report_name', value: 'second' });
  await tick(); await detail.open('b');
  gate.resolve(report('a', 'stale'));
  assert.deepEqual(await Promise.all([first, queued]), [false, false]);
  assert.deepEqual(writes, ['a']);
  assert.deepEqual(changed, []);
  assert.equal(controller.snapshot().saving, false);
  assert.equal(detail.snapshot().selectedReportId, 'b');
});

test('revoked editing permission prevents dispatch and publication of queued changes', async () => {
  const { detail } = detailFixture(); await detail.open('a');
  let editable = true, writes = 0;
  const gate = deferred();
  const { controller, changed } = mutations(detail, { updateReportField: () => { writes++; return gate.promise; } }, { canEdit: () => editable });
  const first = controller.updateSelectedReportField({ field: 'report_name', value: 'first' });
  const queued = controller.updateSelectedReportField({ field: 'report_name', value: 'second' });
  await tick(); editable = false;
  gate.resolve(report('a', 'stale'));
  assert.deepEqual(await Promise.all([first, queued]), [false, false]);
  assert.equal(await controller.updateSelectedReportField({ field: 'report_name', value: 'third' }), false);
  assert.equal(writes, 1); assert.deepEqual(changed, []);
  assert.equal(controller.snapshot().saving, false);
  assert.equal(detail.snapshot().selectedReport.report_name, 'a');
});

test('source preview owns URL replacement, selection cleanup and stale text reads', async () => {
  const created = [], revoked = [], text = deferred();
  const { ReportSourceActions } = loadModule('features/reports/model/sources.ts', {
    URL: { createObjectURL: blob => { const url = `blob:${created.length}`; created.push({ blob, url }); return url; }, revokeObjectURL: url => revoked.push(url) },
  });
  const { detail } = detailFixture(); await detail.open('a');
  let reads = 0;
  const source = new ReportSourceActions(detail, {
    read: async () => ++reads === 3 ? { type: 'text/plain', text: () => text.promise } : new Blob(['preview'], { type: 'application/pdf' }),
    onError: noop,
  });
  const file = { resource_id: 'file', mime_type: 'application/pdf' };
  await source.openSourceFile(file);
  await source.openSourceFile(file);
  assert.deepEqual(revoked, ['blob:0']);
  const pending = source.openSourceFile(file); await tick();
  detail.clear();
  text.resolve('late source text'); await pending;
  source.clearSourcePreview();
  assert.equal(created.length, 2);
  assert.deepEqual(revoked, ['blob:0', 'blob:1']);
  assert.equal(source.snapshot().sourcePreview, null);
  assert.equal(source.snapshot().sourcePreviewLoading, false);
});

test('deleting a report cancels its pending detail request', async () => {
  const gate = deferred();
  const { detail } = detailFixture({ read: () => gate.promise });
  const opening = detail.open('a'); await tick();
  assert.equal(detail.remove(['a']), true);
  gate.resolve(report('a')); assert.equal(await opening, null);
  assert.equal(detail.snapshot().selectedReportId, null);
  assert.equal(detail.snapshot().detailLoading, false);
});

test('a failed lab update retains the original failure when detail refresh also fails', async () => {
  let reads = 0;
  const { detail } = detailFixture({ read: async (_member, id) => {
    if (++reads > 1) throw Error('readback failure'); return report(id);
  } });
  await detail.open('a');
  const { controller, errors } = mutations(detail, { deleteReportLabItem: async () => { throw Error('original failure'); } });
  assert.equal(await controller.deleteSelectedReportLabItem('item'), false);
  assert.equal(errors.at(-1), 'original failure');
  assert.equal(controller.snapshot().labItemMutation, null);
});

test('analysis submission owns its busy state and opens the returned conversation once', async () => {
  const { detail } = detailFixture(); await detail.open('a');
  const requests = [], opened = [];
  const { ReportAnalysisActions } = loadModule('features/reports/model/analysis.ts', {}, {
    '../../../api/client': { apiClient: { sendMessage: async input => { requests.push(input); return { session_id: 'session' }; } } },
  });
  const analysis = new ReportAnalysisActions(detail, {
    canEdit: () => true, deletingAnalysis: () => false,
    model: () => ({ selectedModelId: 'model', thinkingMode: 'off' }),
    onConversationStarted: id => opened.push(id), onError: noop, onMessage: noop,
  });
  assert.equal(await analysis.analyzeSelectedReport('initial'), true);
  assert.equal(requests.length, 1);
  assert.equal(requests[0].contextResources[0].resource_id, 'a');
  assert.equal(requests[0].modelId, 'model');
  assert.deepEqual(opened, ['session']);
  assert.equal(detail.snapshot().detailVisible, false);
  assert.equal(analysis.snapshot().analyzing, false);
  assert.equal(analysis.snapshot().latestAnalysisReportId, 'a');
  analysis.forget(['a']); assert.equal(analysis.snapshot().latestAnalysisReportId, null);
});

test('a late analysis submission cannot navigate away from a newly selected report', async () => {
  const { detail } = detailFixture(); await detail.open('a');
  const gate = deferred(), opened = [];
  const { ReportAnalysisActions } = loadModule('features/reports/model/analysis.ts', {}, {
    '../../../api/client': { apiClient: { sendMessage: () => gate.promise } },
  });
  const analysis = new ReportAnalysisActions(detail, {
    canEdit: () => true, deletingAnalysis: () => false,
    model: () => ({ selectedModelId: 'model', thinkingMode: 'off' }),
    onConversationStarted: id => opened.push(id), onError: noop, onMessage: noop,
  });
  const pending = analysis.analyzeSelectedReport('initial');
  await detail.open('b'); gate.resolve({ session_id: 'late' });
  assert.equal(await pending, false); assert.deepEqual(opened, []);
  assert.equal(detail.snapshot().selectedReportId, 'b');
  assert.equal(detail.snapshot().detailVisible, true);
  assert.equal(analysis.snapshot().analyzing, false);
});
