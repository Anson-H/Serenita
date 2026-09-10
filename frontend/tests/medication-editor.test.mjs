import assert from 'node:assert/strict';
import test from 'node:test';
import { hookRenderer } from './helpers/hook-renderer.mjs';
import { loadModule } from './helpers/load-module.mjs';

const tick = () => new Promise(resolve => setImmediate(resolve));
const medication = {
  medication_id: 'drug', member_id: 'member', generic_name: '示例药品', brand_name: null,
  strength: '5 mg', package_specification: null, prescription_type: 'unknown',
  leaflet_url: 'https://example.com/leaflet', notes: null, sources: [{ resource_id: 'original' }],
  created_at: '2026-09-01', updated_at: '2026-09-01', server_projection: 'read only',
};
const plan = {
  medication_plan_id: 'plan', medication_id: 'drug', member_id: 'member',
  medication_identity: { generic_name: '示例药品' }, starts_at: '2026-09-01T00:00:00+08:00',
  ends_at: null, start_precision: 'date', end_precision: null, timezone: 'Asia/Shanghai',
  dose_text: '1 片', route: null, schedule: null, usage_status: 'taking', notes: null,
  time_status: 'ongoing', created_at: '2026-09-01', updated_at: '2026-09-01',
};

function editorHarness(kind, initial, persist) {
  const renderer = hookRenderer();
  let item = initial;
  const calls = [];
  const { useMedicationEditor } = loadModule('features/medications/useMedicationEditor.ts', { window: globalThis }, {
    react: renderer.react,
    '../../utils/useActiveScope': { useActiveScope: () => () => true },
    '../../api/medicationApi': {
      saveMedication: async (...args) => {
        calls.push(args);
        return persist ? persist(...args) : { ...item, ...args[2] };
      },
      deleteMedication: async () => {},
      saveMedicationCatalog: async (...args) => {
        calls.push(args);
        return persist ? persist(...args) : { ...item, ...args[0] };
      },
      deleteMedicationCatalog: async () => {},
    },
  });
  renderer.render(() => useMedicationEditor('member', kind, item, true, saved => { item = saved; }, () => {}, kind === 'medication'));
  return { renderer, calls };
}

test('medication edits preserve prescription and leaflet fields without submitting response metadata', async () => {
  const { renderer, calls } = editorHarness('medication', medication);
  try {
    renderer.value.change({ prescription_type: 'prescription', leaflet_url: null });
    renderer.render();
    assert.equal(await renderer.value.flush(), true);
    renderer.render();
    assert.equal(calls.length, 1);
    assert.deepEqual(calls[0].slice(0, 2), [{ prescription_type: 'prescription', leaflet_url: null }, 'drug']);
    assert.equal(renderer.value.draft.prescription_type, 'prescription');
    assert.equal(renderer.value.draft.leaflet_url, null);
    assert.equal(renderer.value.dirty, false);
    assert.equal('server_projection' in renderer.value.draft, false);
  } finally { renderer.unmount(); }
});

test('selecting a plan medication submits its reference and pending dose without submitting the display identity', async () => {
  const replacement = { generic_name: '另一药品' };
  const { renderer, calls } = editorHarness('plan', plan, async (_member, _kind, changes) => ({ ...plan, ...changes, medication_identity: replacement }));
  try {
    renderer.value.change({ dose_text: '2 片' });
    renderer.value.selectMedication('other-drug', replacement);
    assert.equal(await renderer.value.flush(), true);
    renderer.render();
    assert.equal(calls.length, 1);
    assert.deepEqual(calls[0].slice(0, 4), ['member', 'plan', { medication_id: 'other-drug', dose_text: '2 片' }, 'plan']);
    assert.equal(renderer.value.identity.generic_name, '另一药品');
    assert.equal(renderer.value.dirty, false);
  } finally { renderer.unmount(); }
});

test('an edit made during medication save is submitted after acknowledgement and keeps its field type', async () => {
  let release;
  const gate = new Promise(resolve => { release = resolve; });
  let server = medication;
  const { renderer, calls } = editorHarness('medication', medication, async (changes) => {
    if (calls.length === 1) await gate;
    server = { ...server, ...changes };
    return server;
  });
  try {
    renderer.value.change({ generic_name: '新名称' });
    const saving = renderer.value.flush();
    await tick();
    renderer.render();
    renderer.value.change({ prescription_type: 'nonprescription' });
    release();
    assert.equal(await saving, true);
    renderer.render();
    assert.deepEqual(calls.map(call => call[0]), [{ generic_name: '新名称' }, { prescription_type: 'nonprescription' }]);
    assert.equal(renderer.value.draft.generic_name, '新名称');
    assert.equal(renderer.value.draft.prescription_type, 'nonprescription');
    assert.equal(renderer.value.dirty, false);
  } finally { release(); renderer.unmount(); }
});
