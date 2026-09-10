import {expect,test} from '@playwright/test';
import {mockWorkspace} from '../helpers/workspace';

test('report navigation waits for the latest draft and a failed save keeps the page',async({page})=>{
 await mockWorkspace(page);
 let report={report_id:'report',member_id:'self',report_name:'检查记录',report_type:'检查报告',report_time:'2026-09-08T08:00:00+08:00',institution_name:'原机构',created_at:'2026-09-08',updated_at:'2026-09-08',has_analysis:false,analysis_outdated:false,sources:[],examination_report:{exam_name:'检查'},analysis_updated_at:null};
 const writes:string[]=[];let fail=false;const releases:(()=>void)[]=[];
 await page.route('**/api/members/self/reports',r=>r.fulfill({json:{reports:[report],total:1}}));
 await page.route('**/api/members/self/reports/report',r=>r.fulfill({json:report}));
 await page.route('**/api/members/self/reports/report/fields',async r=>{
  const value=r.request().postDataJSON().value;writes.push(value);
  await new Promise<void>(resolve=>releases.push(resolve));
  if(fail)return r.fulfill({status:503,json:{detail:{message:'保存暂时失败'}}});
  report={...report,institution_name:value};return r.fulfill({json:report});
 });
 await page.goto('/reports/self/report');await page.getByRole('button',{name:'编辑就诊机构',exact:true}).click();
 const input=page.getByRole('textbox',{name:'就诊机构',exact:true});await input.fill('第一次');await input.press('Tab');
 await expect.poll(()=>writes).toEqual(['第一次']);await input.fill('继续输入');releases[0]();
 await expect.poll(()=>writes).toEqual(['第一次','继续输入']);await expect(input).toHaveValue('继续输入');
 fail=true;await page.getByRole('button',{name:'发起新聊天',exact:true}).click();releases[1]();
 await expect(page).toHaveURL(/\/reports\/self\/report$/);await expect(input).toHaveValue('继续输入');
 fail=false;await page.getByRole('button',{name:'发起新聊天',exact:true}).click();
 await expect.poll(()=>writes.length).toBe(3);releases[2]();await expect(page).toHaveURL('/');
 expect(report.institution_name).toBe('继续输入');
});
