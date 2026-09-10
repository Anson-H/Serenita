import { expect, test, type Locator } from '@playwright/test';
import { mockWorkspace } from '../helpers/workspace';
import type { AddedModel } from '../../src/api/modelTypes';

async function balanced(surface: Locator, childSelector = ':scope > :visible') {
  await expect(surface).toBeVisible();
  await expect.poll(async () => surface.evaluate(element => {
    const e = element as HTMLElement, s = getComputedStyle(e);
    const actual = e.offsetWidth - e.clientWidth - parseFloat(s.borderLeftWidth) - parseFloat(s.borderRightWidth);
    return Math.abs(parseFloat(s.paddingLeft) - parseFloat(s.paddingRight) - actual);
  })).toBeLessThan(1);
  const child = surface.locator(childSelector).first();
  await expect(child).toBeVisible();
  const outer = (await surface.boundingBox())!, inner = (await child.boundingBox())!;
  expect(Math.abs(inner.x - outer.x - (outer.x + outer.width - inner.x - inner.width))).toBeLessThan(1.1);
  expect(inner.width).toBeLessThanOrEqual(750.1);
  expect(inner.x - outer.x).toBeGreaterThanOrEqual(14.5);
}

for (const width of [390, 820, 1600]) {
  test(`detail insets remain balanced with actual scrollbars at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 700 });
    const profile = { availability: 'available' as const, supports_text: true, file_mime_types: ['image/png'], supports_tool_calling: true };
    const model: AddedModel = { model_id: 'test:chat', provider_id: 'test', remote_model_id: 'chat', model_name: '生成示例', model_type: 'generation', thinking_modes: ['default'], capability_profiles: { default_state: 'non_thinking', non_thinking: profile, thinking: { ...profile, availability: 'unavailable' } }, context_window_tokens: 32000, max_output_tokens: 2000, supports_text: true, file_mime_types: ['image/png'], supports_tool_calling: true, embedding_capabilities: null, embedding_dimensions: null, max_input_tokens: null, max_batch_size: null };
    await mockWorkspace(page, [model]);
    await page.route('**/api/model-providers', r => r.fulfill({ json: { providers: [{ provider_id: 'test', provider_name: '测试提供方', api_url: 'https://test.invalid/v1', has_api_key: true, is_configured: true }] } }));
    const report = { report_id: 'report', member_id: 'self', report_name: '检查记录', report_type: '检查报告', report_time: '2026-09-08T08:00:00+08:00', institution_name: '测试机构', created_at: '', updated_at: '', has_analysis: false, analysis_outdated: false, sources: [], examination_report: { exam_name: '检查' }, analysis_updated_at: null };
    await page.route('**/api/members/self/reports', r => r.fulfill({ json: { reports: [report], total: 1 } }));
    await page.route('**/api/members/self/reports/report', r => r.fulfill({ json: report }));
    const log = { medical_log_id: 'log', member_id: 'self', title: '复诊记录', content: '记录\n'.repeat(40), recorded_on: '2026-09-01', created_at: '', updated_at: '' };
    await page.route('**/api/members/self/medical-logs**', r => r.fulfill({ json: new URL(r.request().url()).pathname.endsWith('/log') ? { medical_log: log } : { member_id: 'self', medical_logs: [{ ...log, summary: '复诊' }] } }));
    await page.route('**/api/members/self/medical-history', r => r.fulfill({ json: { member_id: 'self', history: Object.fromEntries(['past_medical_history', 'surgical_trauma_history', 'allergy_history', 'transfusion_vaccination_history', 'birth_occupational_history', 'lifestyle_history', 'family_history', 'special_history'].map(k => [k, { text: null, updated_at: null }])) } }));
    await page.route('**/api/members/self/body-metrics/**', r => r.fulfill({ json: new URL(r.request().url()).pathname.endsWith('/catalog') ? { metrics: [], meal_types: { breakfast: '早餐' }, stages: {} } : new URL(r.request().url()).pathname.endsWith('/records') ? { items: [], total: 0, next_offset: null } : { series: [], sources: [], total_records: 0, coverage_from: null, coverage_to: null } }));
    const drug = { medication_id: 'drug', member_id: 'self', generic_name: '药品', prescription_type: 'unknown', notes: null, sources: [], batches: [] };
    const plan = { medication_plan_id: 'plan', member_id: 'self', medication_id: 'drug', medication_identity: { generic_name: '药品' }, time_status: 'ongoing', notes: null, starts_at: '2026-09-01T00:00:00+08:00', ends_at: null, start_precision: 'date', end_precision: null, timezone: 'Asia/Shanghai', dose_text: '1 片', usage_status: 'unknown', schedule: { kind: 'daily', times: [{ time: '08:00' }] } };
    await page.route('**/api/members/self/medications**', r => r.fulfill({ json: new URL(r.request().url()).pathname.endsWith('/drug') ? drug : { items: [drug], next_cursor: null } }));
    await page.route('**/api/members/self/medication-plans**', r => r.fulfill({ json: new URL(r.request().url()).pathname.endsWith('/plan') ? plan : { items: [plan], next_cursor: null } }));
    await page.route('**/api/notifications?*', r => r.fulfill({ json: { items: Array.from({ length: 30 }, (_, i) => ({ notification_id: 'n' + i, title: '回答已生成', message: '聊天内容', notification_type: 'answer_completed', occurred_at: '2026-09-01', available_at: '2026-09-01', status: 'pending', target: { resource_type: 'conversation', resource_id: 'chat' }, actions: ['read'], details: [] })), next_cursor: null, errors: [] } }));
    await page.goto('/setting');
    await page.locator('.settings-nav').getByRole('button', { name: '通知', exact: true }).click();
    await balanced(page.locator('.settings-detail-panel-body'));
    await page.goto('/setting');
    await page.locator('.settings-nav').getByRole('button', { name: '模型提供方', exact: true }).click();
    await page.getByRole('button', { name: '测试提供方', exact: true }).click();
    await page.getByRole('button', { name: '打开模型详情：chat', exact: true }).click();
    await balanced(page.locator('.model-settings-panel-body'));
    const modelBody = (await page.locator('.model-settings-panel-body').boundingBox())!;
    const wrapper = (await page.locator('.settings-detail-panel-body').boundingBox())!;
    expect(modelBody.x).toBeCloseTo(wrapper.x, 0);
    expect(modelBody.width).toBeCloseTo(wrapper.width, 0);
    await page.goto('/reports/self/report');
    await balanced(page.locator('.report-detail-scroll'));
    await page.goto('/reports');
    await page.getByRole('button', { name: '查看本人的个人信息', exact: true }).click();
    await balanced(page.locator('.member-information-scroll'));
    await page.goto('/health/self/medical-logs/log');
    await balanced(page.locator('.medical-log-form'));
    await page.goto('/health/self/body-metrics/nutrition');
    await balanced(page.locator('.bm-detail-scroll'));
    await page.goto('/health/self/medications/catalog/drug');
    await balanced(page.locator('.report-detail-scroll'));
    await page.goto('/health/self/medications/plans/plan');
    await balanced(page.locator('.report-detail-scroll'));
    for (const name of ['用药频率', '用药时间']) {
      await page.getByRole('button', { name, exact: true }).click();
      await balanced(page.locator('.report-detail-scroll'));
      await expect(page.locator('.medication-schedule-body')).toHaveCSS('padding-left', '0px');
      await page.locator('.medication-detail > .workspace-navigation-toolbar').getByRole('button', { name: '返回上一级', exact: true }).click();
    }
    await page.goto('/notifications');
    await balanced(page.locator('.notification-list'));
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  });
}

test('local scrolling menus remeasure when overflow appears and disappears', async ({ page }) => {
  await mockWorkspace(page);
  await page.goto('/chat');
  await expect(page.locator('.conversation-composer')).toBeVisible();
  await page.evaluate(() => {
    const e = document.createElement('div');
    e.id = 'local-scroll-probe'; e.className = 'select-popover-options scroll-balanced';
    e.style.cssText = 'position:fixed;top:100px;left:100px;width:200px;height:100px;overflow:auto';
    e.innerHTML = '<div style="height:300px">选项</div>';
    document.body.append(e);
  });
  const surface = page.locator('#local-scroll-probe');
  for (const height of [300, 20, 300]) {
    await surface.locator('div').evaluate((e, h) => (e as HTMLElement).style.height = `${h}px`, height);
    await expect.poll(() => surface.evaluate(e => {
      const s = getComputedStyle(e), actual = (e as HTMLElement).offsetWidth - e.clientWidth;
      return { measurement: parseFloat(s.getPropertyValue('--scrollbar-layout-width')) - actual, balance: parseFloat(s.paddingLeft) - parseFloat(s.paddingRight) - actual };
    })).toEqual({ measurement: 0, balance: 0 });
  }
});

for (const width of [300, 820, 1280]) test(`file preview title stays centered beside all actions at ${width}px`, async ({ page }) => {
  await mockWorkspace(page);
  await page.setViewportSize({ width, height: 700 });
  await page.goto('/chat');
  await expect(page.locator('.conversation-composer')).toBeVisible();
  await page.evaluate(`(async () => {
    const {default:React} = await import('/node_modules/.vite/deps/react.js');
    const {default:ReactDOM} = await import('/node_modules/.vite/deps/react-dom_client.js');
    const {FilePreview} = await import('/src/components/FilePreview.tsx');
    const container = document.createElement('div'); document.body.append(container);
    const file = {id:'a',name:'很长的原件名称'.repeat(20)+'.txt',mimeType:'text/plain'};
    ReactDOM.createRoot(container).render(React.createElement(FilePreview, {file, files:[file], objectUrl:URL.createObjectURL(new Blob(['原件内容'],{type:'text/plain'})), textContent:'原件内容\\n'.repeat(100), onDelete:()=>{}, onSelect:()=>{}, onClose:()=>{}}));
  })()`);
  const title = page.locator('.file-preview-heading');
  await expect(title).toBeVisible();
  await expect.poll(async () => {
    const header = (await page.locator('.file-preview .dialog-titlebar').boundingBox())!, box = (await title.boundingBox())!;
    return Math.abs(box.x + box.width / 2 - header.x - header.width / 2);
  }).toBeLessThan(1);
  const box = (await title.boundingBox())!, actions = (await page.locator('.file-preview-actions').boundingBox())!;
  expect(box.x + box.width).toBeLessThanOrEqual(actions.x);
  expect(actions.x + actions.width).toBeLessThanOrEqual(width);
  await expect(title).toHaveCSS('text-overflow', 'ellipsis');
});
