import { expect, test } from '@playwright/test';
import { mockWorkspace } from '../helpers/workspace';

for (const width of [1280, 820, 390]) {
  test(`report creation inherits each entry and fields do not rename the step at ${width}px`, async ({ page }, testInfo) => {
    await page.setViewportSize({ width, height: 900 });
    await mockWorkspace(page);
    await page.route('**/api/members/self/lab-dictionary', route => route.fulfill({ json: {
      dictionary_revision: '1', summary: { item_count: 0, category_count: 2, relation_count: 0 }, items: [], relations: [],
      categories: ['肝功能', '血常规'].map(category_name => ({ category_name, item_count: 0, primary_item_count: 0, related_item_count: 0, result_count: 0, report_count: 0 })),
    } }));
    await page.goto('/reports');
    await page.getByRole('button', { name: '创建医疗报告', exact: true }).click();
    const dialog = page.locator('.report-create-dialog');
    const heading = dialog.locator('.dialog-titlebar h2');
    await expect(heading).toHaveText('创建医疗报告');
    await dialog.getByRole('button', { name: /文字录入/ }).click();
    await expect(heading).toHaveText('文字录入');
    const names = await dialog.locator('.report-create-type-list strong').allTextContents();
    expect(names).toHaveLength(7);
    for (const name of names) {
      await dialog.getByRole('button', { name: new RegExp(`^${name}`) }).click();
      await expect(heading).toHaveText(name);
      await expect(dialog).toHaveAccessibleName(name);
      await expect(dialog.locator('.report-create-form-scroll > .content-description')).toHaveCount(0);
      if (name === '检验报告') {
        await dialog.getByRole('button', { name: '医疗报告名称', exact: true }).click();
        await page.getByRole('option', { name: '肝功能', exact: true }).click();
        await expect(heading).toHaveText('检验报告');
        await dialog.screenshot({ path: testInfo.outputPath('report-title.png') });
      }
      await dialog.getByRole('button', { name: '返回上一级', exact: true }).click();
      await expect(heading).toHaveText('文字录入');
    }
    await dialog.getByRole('button', { name: '返回上一级', exact: true }).click();
    await expect(heading).toHaveText('创建医疗报告');
    await dialog.getByRole('button', { name: '关闭创建医疗报告', exact: true }).click();
    await page.getByRole('button', { name: '创建医疗报告', exact: true }).click();
    await expect(heading).toHaveText('创建医疗报告');
  });

  test(`log titles follow entry, saved rename and direct navigation at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    await mockWorkspace(page);
    let log = { medical_log_id: 'log', member_id: 'self', title: '复诊记录', content: '复诊后记录', recorded_on: '2026-09-01', created_at: '', updated_at: '' };
    await page.route('**/api/members/self/medical-logs**', route => {
      if (new URL(route.request().url()).pathname.endsWith('/log')) {
        if (route.request().method() === 'PATCH') log = { ...log, ...route.request().postDataJSON() };
        return route.fulfill({ json: { medical_log: log } });
      }
      return route.fulfill({ json: { member_id: 'self', medical_logs: [{ ...log, summary: log.content }] } });
    });
    await page.goto('/health/self/medical-logs');
    await page.getByRole('button', { name: '创建健康日记', exact: true }).click();
    const create = page.getByRole('dialog', { name: '创建健康日记', exact: true });
    await create.getByLabel('日记标题', { exact: true }).fill('新草稿');
    await expect(create.locator('.dialog-titlebar h2')).toHaveText('创建健康日记');
    await create.getByRole('button', { name: '关闭创建健康日记', exact: true }).click();
    await page.locator('.report-timeline-item').click();
    const title = page.locator('.medical-log-detail .workspace-navigation-title');
    await expect(title).toHaveText('复诊记录');
    await page.getByLabel('日记标题', { exact: true }).fill('复诊后的补充记录');
    await page.getByLabel('日记标题', { exact: true }).press('Tab');
    await expect(title).toHaveText('复诊后的补充记录');
    if (width <= 650) await page.locator('.medical-log-detail').getByRole('button', { name: '返回上一级', exact: true }).click();
    await expect(page.locator('.report-timeline-copy strong')).toHaveText('复诊后的补充记录');
    await page.goto('/health/self/medical-logs/log');
    await expect(title).toHaveText('复诊后的补充记录');
    await page.reload();
    await expect(title).toHaveText('复诊后的补充记录');
  });

  test(`report object title survives direct entry and long names at ${width}px`, async ({ page }, testInfo) => {
    await page.setViewportSize({ width, height: 900 });
    await mockWorkspace(page);
    const name = '门诊复查报告与长期随访记录'.repeat(8);
    const report = { report_id: 'report', member_id: 'self', report_name: name, report_type: '检查报告', report_time: '2026-09-08T08:00:00+08:00', institution_name: '测试机构', created_at: '', updated_at: '', has_analysis: false, analysis_outdated: false, sources: [], examination_report: { exam_name: '检查' }, analysis_updated_at: null };
    await page.route('**/api/members/self/reports', r => r.fulfill({ json: { reports: [report], total: 1 } }));
    await page.route('**/api/members/self/reports/report', r => r.fulfill({ json: report }));
    await page.goto('/reports/self/report');
    const title = page.locator('.reports-detail-toolbar .workspace-navigation-title');
    await expect(title).toHaveText(name);
    await expect(title).toHaveAttribute('title', name);
    await expect(title).toHaveAccessibleName(name);
    await expect(title).toHaveCSS('text-overflow', 'ellipsis');
    const header = title.locator('..');
    const titleBox = (await title.boundingBox())!;
    const leadingBox = (await header.locator('.workspace-navigation-leading').boundingBox())!;
    const favoriteBox = (await header.getByRole('button', { name: '收藏医疗报告', exact: true }).boundingBox())!;
    expect(titleBox.x).toBeGreaterThanOrEqual(leadingBox.x + leadingBox.width);
    expect(titleBox.x + titleBox.width).toBeLessThanOrEqual(favoriteBox.x);
    await header.screenshot({ path: testInfo.outputPath('long-title.png') });
    if (width <= 650) await header.getByRole('button', { name: '返回上一级', exact: true }).click();
    else await page.goto('/reports');
    await page.locator('.report-timeline-item').click();
    await expect(title).toHaveText(name);
    await page.reload();
    await expect(title).toHaveText(name);
  });

  test(`settings and favorites retain their entry names at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    await mockWorkspace(page);
    for (const name of ['账号资料', '密码安全', '授权管理', '通知', '主题', '健康档案', '默认模型', '联网工具', '模型提供方', '聊天设置', '检验分类目录', '检验指标目录']) {
      await page.goto('/setting');
      await page.locator('.settings-nav').getByRole('button', { name, exact: true }).click();
      await expect(page.locator('.settings-toolbar .workspace-navigation-title')).toHaveText(name);
    }
    await page.goto('/favorites');
    await expect(page.locator('.favorites-list-toolbar .workspace-navigation-title')).toHaveText('我的收藏');
  });
}
