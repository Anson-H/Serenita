import { expect, test } from "@playwright/test";
import { mockWorkspace } from "../helpers/workspace";

for (const width of [1280, 390]) {
  test(`report filters combine and preserve values while switching at ${width}px`, async ({ page }, testInfo) => {
    await mockWorkspace(page);
    const reports = [
      { report_id: "early", report_name: "血常规", report_type: "检验报告", report_time: "2026-09-01T00:00:00+08:00" },
      { report_id: "late", report_name: "血常规复查", report_type: "检验报告", report_time: "2026-09-02T23:59:59+08:00" },
      { report_id: "exam", report_name: "胸部检查", report_type: "检查报告", report_time: "2026-09-02T10:00:00+08:00" }
    ].map(report => ({ ...report, member_id: "self", institution_name: "社区医院", has_analysis: false, analysis_outdated: false, flagged_count: 0, total_count: 0, created_at: report.report_time, updated_at: report.report_time }));
    await page.route("**/api/members/self/reports", route => route.fulfill({ json: { reports, total: reports.length } }));
    await page.setViewportSize({ width, height: 844 });
    await page.goto("/reports");
    const bar = page.locator(".report-filter-bar");
    const rows = page.locator(".report-timeline-item");
    await expect(rows).toHaveCount(3);
    await expect(page.locator('.object-list-count')).toHaveText('共 3 份医疗报告');
    await bar.getByRole("button", { name: "展开搜索栏", exact: true }).click();
    await bar.getByRole("searchbox").fill("血常规");
    await expect(rows).toHaveCount(2);
    await bar.getByRole("button", { name: "展开日期范围栏", exact: true }).click();
    for (const label of ["起始日期", "结束日期"]) {
      await bar.getByRole("button", { name: label, exact: true }).click();
      const picker = page.getByRole("dialog", { name: `${label}选择器` });
      await picker.getByRole("textbox", { name: "年份", exact: true }).fill("2026");
      await picker.getByRole("textbox", { name: "月份", exact: true }).fill("09");
      await picker.getByRole("textbox", { name: "日期", exact: true }).fill("02");
      await picker.getByRole("button", { name: "完成", exact: true }).click();
    }
    await expect(rows).toHaveCount(1);
    await expect(rows).toContainText("血常规复查");
    await expect(page.locator('.object-list-count')).toHaveText('共 1 份医疗报告');
    await expect(bar.getByText("起始日期", { exact: true })).toHaveCount(0);
    const bounds = await bar.locator(":scope > *").evaluateAll(elements => elements.map(el => {
      const rect = el.getBoundingClientRect();
      return { y: rect.y, height: rect.height, overflow: el.scrollWidth - el.clientWidth };
    }));
    expect(bounds).toHaveLength(3);
    expect(Math.max(...bounds.map(b => b.y)) - Math.min(...bounds.map(b => b.y))).toBeLessThan(1);
    expect(Math.max(...bounds.map(b => b.overflow))).toBeLessThanOrEqual(1);
    await bar.getByRole("button", { name: "展开类型筛选栏", exact: true }).click();
    await bar.getByRole("button", { name: "按医疗报告类型筛选", exact: true }).click();
    await page.getByRole("option", { name: "检验报告", exact: true }).click();
    await page.keyboard.press("Escape");
    await expect(rows).toHaveCount(0);
    await expect(page.locator('.object-list-count')).toHaveCount(0);
    await bar.getByRole("button", { name: "展开搜索栏", exact: true }).click();
    await expect(bar.getByRole("searchbox")).toHaveValue("血常规");
    await bar.getByRole("searchbox").fill("社区医院");
    await expect(rows).toHaveCount(1);
    await expect(rows).toContainText("胸部检查");
    await bar.getByRole("button", { name: "展开日期范围栏", exact: true }).click();
    await expect(bar.getByRole("button", { name: "起始日期", exact: true })).toHaveText("2026年9月2日");
    await expect(bar.getByRole("button", { name: "结束日期", exact: true })).toHaveText("2026年9月2日");
    const originalFilter=(await bar.boundingBox())!,originalRow=(await rows.first().boundingBox())!;
    await rows.first().click({button:'right'});
    await page.getByRole('menuitem',{name:'多选',exact:true}).click();
    const pane=page.locator('.report-library'), heading=pane.locator('.list-selection-heading');
    const scroll=pane.locator('.report-library-scroll'), bottom=pane.locator('.list-bulk-actions');
    for(const button of await heading.getByRole('button').all()){
      await expect(button).toHaveText('');await expect(button).toHaveCSS('width','40px');await expect(button).toHaveCSS('height','40px');
      await expect(button).toHaveAttribute('title',/.+/);
    }
    await expect(heading.getByRole('status')).toHaveCSS('font-size','15px');
    const headingBox=(await heading.boundingBox())!,scrollBox=(await scroll.boundingBox())!,buttonBox=(await bottom.getByRole('button').first().boundingBox())!;
    await expect(bar).toBeHidden();
    expect(headingBox.y).toBeCloseTo(originalFilter.y,0);
    expect((await rows.first().boundingBox())!.y).toBeCloseTo(originalRow.y,0);
    expect(scrollBox.y-headingBox.y-headingBox.height).toBeCloseTo(15,0);
    expect(buttonBox.y-scrollBox.y-scrollBox.height).toBeCloseTo(15,0);
    await expect(scroll).toHaveCSS('padding-bottom','0px');
    await pane.screenshot({path:testInfo.outputPath(`report-selection-spacing-${width}.png`)});
    await heading.getByRole('button',{name:'退出医疗报告多选',exact:true}).click();
    await expect(bar).toBeVisible();
    await expect(bar.getByRole('button',{name:'起始日期',exact:true})).toHaveText('2026年9月2日');
    expect((await rows.first().boundingBox())!.y).toBeCloseTo(originalRow.y,0);
  });
}


test.describe('touch date picker', () => {
  test.use({hasTouch:true, viewport:{width:390,height:844}});
  test('compact text retains touch targets in the calendar', async ({page}) => {
    await mockWorkspace(page);
    await page.goto('/reports');
    await page.getByRole('button',{name:'展开日期范围栏',exact:true}).click();
    await page.getByRole('button',{name:'起始日期',exact:true}).click();
    const picker = page.getByRole('dialog',{name:'起始日期选择器',exact:true});
    await expect(picker.getByRole('textbox',{name:'年份',exact:true})).toHaveCSS('font-size','13px');
    const bounds = await picker.getByRole('gridcell').first().boundingBox();
    expect(bounds!.height).toBeGreaterThanOrEqual(44);
    expect(bounds!.width).toBeGreaterThanOrEqual(44);
    const panel = (await picker.boundingBox())!;
    expect(panel.x).toBeGreaterThanOrEqual(15);
    expect(panel.x + panel.width).toBeLessThanOrEqual(375);
  });
});
