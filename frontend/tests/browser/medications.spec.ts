import {expect,test} from '@playwright/test';
import {mockWorkspace} from '../helpers/workspace';
import {MEDICAL_HISTORY_FIELDS} from '../../src/api/medicalHistoryTypes';
const medication={medication_id:'drug1',member_id:'self',strength:'5 mg',generic_name:'示例药品',brand_name:null,package_specification:null,prescription_type:'unknown',notes:null,sources:[],batches:[],created_at:'2026-09-01T00:00:00Z',updated_at:'2026-09-01T00:00:00Z'};
async function setup(page:Parameters<typeof mockWorkspace>[0]){
 await mockWorkspace(page);let saved={...medication};
 await page.route('**/api/members/self/medications**',async route=>{
   const req=route.request();const url=new URL(req.url());
   if(req.method()==='PATCH'){saved={...saved,...req.postDataJSON(),updated_at:new Date().toISOString()};return route.fulfill({json:saved});}
   if(req.method()==='POST')return route.fulfill({status:201,json:{...medication,...req.postDataJSON()}});
   if(url.pathname.endsWith('/drug1'))return route.fulfill({json:saved});
   return route.fulfill({json:{items:[saved],next_cursor:null}});
 });
 await page.route('**/api/medication-catalog**',route=>{
   const req=route.request();if(req.method()==='PATCH')saved={...saved,...req.postDataJSON()};
   return route.fulfill({json:new URL(req.url()).pathname.endsWith('/drug1')?saved:{items:[saved],total:1,next_cursor:null}});
 });
 return ()=>saved;
}
async function selectPlanDrug(page:Parameters<typeof mockWorkspace>[0]){
 await page.getByRole('button',{name:'切换药品',exact:true}).click();
 const picker=page.getByRole('dialog',{name:'切换药品',exact:true});
 await expect(picker.getByRole('button',{name:'手动录入',exact:true})).toHaveCount(0);
 await picker.getByRole('button',{name:/示例药品/}).click();
}
for(const width of [1280,390])for(const section of ['catalog','plans'])test(`medication and member details share one titlebar in ${section} at ${width}px`,async({page})=>{
 await setup(page);await page.setViewportSize({width,height:900});
 const plan={medication_id:'drug1',medication_plan_id:'plan1',member_id:'self',medication_identity:{generic_name:'计划药品'},starts_at:'2026-09-07T00:00:00Z',start_precision:'date',timezone:'UTC',schedule:null};
 await page.route('**/api/members/self/medication-plans**',route=>route.fulfill({json:new URL(route.request().url()).pathname.endsWith('/plan1')?plan:{items:[plan],next_cursor:null}}));
 await page.route('**/api/members/self/medical-history',route=>route.fulfill({json:{member_id:'self',history:Object.fromEntries(MEDICAL_HISTORY_FIELDS.map(([field])=>[field,{text:null,updated_at:null}]))}}));
 const id=section==='catalog'?'drug1':'plan1';await page.goto(`/health/self/medications/${section}/${id}`);
 const detail=page.locator('.medication-detail');await expect(detail.locator('.medication-editor')).toBeVisible();
 await expect(detail.locator('.workspace-navigation-toolbar')).toHaveCount(1);
 if(width===390)await detail.getByRole('button',{name:'返回上一级',exact:true}).click();
 for(let attempt=0;attempt<2;attempt++){
  await page.getByRole('button',{name:'查看本人的个人信息',exact:true}).click();
  await expect(detail.getByRole('heading',{name:'本人',exact:true})).toHaveCount(1);
  await expect(detail.locator('.workspace-navigation-toolbar')).toHaveCount(1);
  await expect(detail.locator(':scope > .member-information-detail')).toHaveCount(1);
  await expect(detail.locator('.report-detail-scroll')).toHaveCount(0);
  await expect(page.locator('.report-timeline-item[aria-current="page"]')).toHaveCount(0);
  const outer=(await detail.boundingBox())!;const bar=(await detail.locator('.workspace-navigation-toolbar').boundingBox())!;
  expect(Math.abs(outer.y-bar.y)).toBeLessThan(2);
  await detail.getByRole('button',{name:'返回上一级',exact:true}).click();
  await expect(detail.locator('.member-information-detail')).toHaveCount(0);
  if(width===1280)await expect(detail.locator('.medication-editor')).toBeVisible();
  else await expect(page.getByRole('button',{name:'查看本人的个人信息',exact:true})).toBeFocused();
 }
 if(width===390)await page.locator('.report-timeline-item').first().click();
 await expect(detail.locator('.medication-editor')).toBeVisible();
 await expect(detail.locator('.workspace-navigation-toolbar')).toHaveCount(1);
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
});

test('failed medication detail reads stop loading and can be retried',async({page})=>{
 await setup(page);let fail=true;
 await page.route('**/api/members/self/medications/drug1',route=>fail?route.fulfill({status:503,json:{detail:{message:'详情暂时不可用'}}}):route.fallback());
 await page.goto('/health/self/medications/catalog/drug1');
 const detail=page.locator('.medication-detail');await expect(detail.getByRole('alert')).toContainText('详情暂时不可用');
 await expect(detail.getByText('正在读取…',{exact:true})).toHaveCount(0);
 await expect(detail.locator('.workspace-navigation-toolbar')).toHaveCount(1);
 fail=false;await detail.getByRole('button',{name:'重新读取详情',exact:true}).click();
 await expect(detail.locator('.medication-editor')).toBeVisible();await expect(detail.getByRole('alert')).toHaveCount(0);
});

test('new plans require a medicine from the owner account catalog',async({page})=>{
 await setup(page);let creates=0;
 await page.route('**/api/members/self/medications**',route=>route.fulfill({json:{items:[],next_cursor:null}}));
 await page.route('**/api/members/self/medication-plans**',route=>{if(route.request().method()==='POST')creates++;return route.fulfill({json:{items:[],next_cursor:null}});});
 await page.goto('/health/self/medications/plans');
 await page.getByRole('button',{name:'创建用药计划',exact:true}).click();
 const form=page.locator('.creation-dialog');
 await form.getByRole('button',{name:'切换药品',exact:true}).click();
 const picker=page.getByRole('dialog',{name:'切换药品',exact:true});
 await expect(picker.getByText('目录暂无药品，请先在设置的药品目录中添加',{exact:true})).toBeVisible();
 await expect(picker.getByRole('button',{name:/手动录入|搜索药品|已有药品/})).toHaveCount(0);
 await page.keyboard.press('Escape');
 await form.getByRole('button',{name:'完成',exact:true}).click();
 await expect(form.getByRole('alert')).toContainText('请从药品目录中选择药品');
 expect(creates).toBe(0);
});

for(const width of [1280,390])test(`plan filters share one row and retain queries at ${width}px`,async({page})=>{
 await setup(page);await page.setViewportSize({width,height:900});
 const queries:string[]=[];
 await page.route('**/api/members/self/medication-plans**',route=>{queries.push(route.request().url());return route.fulfill({json:{items:[],next_cursor:null}});});
 await page.goto('/health/self/medications/plans');
 const bar=page.locator('.medication-plan-filters');
 async function checkRow(){
  const boxes=await bar.locator(':scope > *').evaluateAll(nodes=>nodes.map(n=>{const b=n.getBoundingClientRect();return {center:b.y+b.height/2,right:b.right};}));
  expect(Math.max(...boxes.map(b=>b.center))-Math.min(...boxes.map(b=>b.center))).toBeLessThan(2);
  const bounds=(await bar.boundingBox())!;expect(Math.max(...boxes.map(b=>b.right))).toBeLessThanOrEqual(bounds.x+bounds.width+1);
 }
 await page.getByRole('button',{name:'用药计划状态',exact:true}).click();
 await page.getByRole('option',{name:'未开始',exact:true}).click();await checkRow();
 await page.getByRole('button',{name:'展开搜索栏',exact:true}).click();
 await page.getByRole('searchbox',{name:'搜索用药资料',exact:true}).fill('眼药');await checkRow();
 await page.getByRole('button',{name:'展开日期范围栏',exact:true}).click();await checkRow();
 await expect(page.getByRole('group',{name:'日期范围',exact:true})).toBeVisible();
 await page.getByRole('button',{name:'展开计划状态栏',exact:true}).click();
 await expect(page.getByRole('button',{name:'用药计划状态',exact:true})).toHaveText('未开始');
 await page.getByRole('button',{name:'展开搜索栏',exact:true}).click();
 await expect(page.getByRole('searchbox',{name:'搜索用药资料',exact:true})).toHaveValue('眼药');
 await expect.poll(()=>new URL(queries.at(-1)!).searchParams.get('query')).toBe('眼药');
 expect(new URL(queries.at(-1)!).searchParams.get('status')).toBe('upcoming');
});

for(const width of [1280,390])test(`plan creation dialog retains its selected medicine and validates dates at ${width}px`,async({page})=>{
 await setup(page);await page.setViewportSize({width,height:720});
 await page.route('**/api/members/self/medication-plans**',route=>route.fulfill({json:{items:[],next_cursor:null}}));
 await page.goto('/health/self/medications/plans');
 const action=page.getByRole('button',{name:'创建用药计划',exact:true});await action.click();
 const dialog=page.locator('.creation-dialog');
 await selectPlanDrug(page);
 await expect(page).toHaveURL(/medications\/plans$/);
 const bounds=(await dialog.boundingBox())!;expect(bounds.y).toBeGreaterThanOrEqual(0);expect(bounds.y+bounds.height).toBeLessThanOrEqual(720);
 await expect(dialog.locator('.medication-plan-identity')).toContainText('示例药品');
 await dialog.getByRole('button',{name:'完成',exact:true}).click();
 await expect(dialog.getByRole('alert')).toContainText('开始日期');
 await dialog.getByRole('button',{name:'关闭创建用药计划',exact:true}).click();
 await expect(dialog).toHaveCount(0);await expect(action).toBeFocused();
});

test('read only medication exposes static fields and files without mutation controls',async({page})=>{
 await setup(page);await page.route('**/api/members',route=>route.fulfill({json:{access_revision:1,default_member_id:'self',initial_member_id:'self',last_member_id:'self',startup_mode:'last_used',members:[{member_id:'self',member_name:'家人',account_id:'owner',owner_account:'owner',is_owned:false,can_edit:false,permission:'read'}]}}));
 await page.goto('/health/self/medications/catalog/drug1');
 await expect(page.locator('.medication-editor').getByText('示例药品',{exact:true})).toBeVisible();
 await expect(page.getByLabel('通用名',{exact:true})).toHaveCount(0);
 await expect(page.getByRole('button',{name:'删除药品',exact:true})).toHaveCount(0);
 await expect(page.getByRole('button',{name:'添加药品批次',exact:true})).toHaveCount(0);
 await expect(page.getByRole('button',{name:'添加药品批次',exact:true})).toHaveCount(0);
});

for(const width of [1280,390])test(`plan identity is compact and a failed drug switch preserves its arrangement at ${width}px`,async({page})=>{
 await setup(page);await page.setViewportSize({width,height:900});
 let fail=true;
 let plan:any={medication_id:'drug1',medication_plan_id:'plan1',member_id:'self',medication_identity:{brand_name:'商品名',generic_name:'原计划药品',strength:'10 mg',package_specification:'12 片 / 盒'},notes:'保留计划备注',starts_at:'2026-09-07T00:00:00Z',start_precision:'date',ends_at:null,end_precision:null,timezone:'UTC',dose_text:'1 片',usage_status:'unknown',schedule:{kind:'daily',times:[{time:'08:00'}]}};
 const arrangement=({starts_at,ends_at,start_precision,end_precision,timezone,dose_text,route,schedule,usage_status}:any)=>({starts_at,ends_at,start_precision,end_precision,timezone,dose_text,route,schedule,usage_status});const original=structuredClone(arrangement(plan));
 await page.route('**/api/members/self/medication-plans**',route=>{
  if(route.request().method()==='PATCH'){const payload=route.request().postDataJSON();expect(payload).not.toHaveProperty('medication_identity');plan={...plan,...payload,medication_identity:{generic_name:medication.generic_name,strength:medication.strength}};return route.fulfill({json:plan});}
  return route.fulfill({json:new URL(route.request().url()).pathname.endsWith('/plan1')?plan:{items:[plan],next_cursor:null}});
 });
 await page.route('**/api/members/self/medications/drug1',route=>fail?route.fulfill({status:503,json:{detail:{message:'药品读取失败'}}}):route.fallback());
 await page.goto('/health/self/medications/plans/plan1');
 const bar=page.getByRole('region',{name:'计划药品',exact:true});
 await expect(bar).toContainText('商品名 原计划药品');await expect(bar).toContainText('10 mg · 12 片 / 盒');
 await expect(page.getByLabel('通用名',{exact:true})).toHaveCount(0);
 await expect(page.getByRole('heading',{name:'药品信息',exact:true})).toHaveCount(0);
 await bar.getByRole('button',{name:'切换药品',exact:true}).click();
 const picker=page.getByRole('dialog',{name:'切换药品',exact:true});
 const choice=picker.getByRole('button',{name:/示例药品/});
 await expect(choice).toBeVisible();
 const alignment=await choice.evaluate(row=>({
  rowLeft:row.getBoundingClientRect().left,padding:parseFloat(getComputedStyle(row).paddingLeft),
  iconLeft:row.querySelector('svg')!.getBoundingClientRect().left,
  titleLeft:row.querySelector('strong')!.getBoundingClientRect().left,
  descriptionLeft:row.querySelector('.content-description')!.getBoundingClientRect().left,
 }));
 expect(alignment.iconLeft).toBeCloseTo(alignment.rowLeft+alignment.padding,0);
 expect(alignment.titleLeft).toBeCloseTo(alignment.descriptionLeft,0);
 await picker.getByRole('button',{name:/示例药品/}).click();await expect(picker.getByRole('alert')).toContainText('药品读取失败');
 expect(plan.medication_identity.generic_name).toBe('原计划药品');
 await page.keyboard.press('Escape');await expect(picker).toHaveCount(0);await expect(bar.getByRole('button',{name:'切换药品',exact:true})).toBeFocused();
 await bar.getByRole('button',{name:'切换药品',exact:true}).click();fail=false;
 await picker.getByRole('button',{name:/示例药品/}).click();
 await expect(picker).toHaveCount(0);await expect(bar).toContainText('示例药品');
 await expect.poll(()=>plan.medication_id).toBe('drug1');expect(arrangement(plan)).toEqual(original);expect(plan.notes).toBe('保留计划备注');
 const columns=await page.locator('.medication-plan-fields .grouped-object-list > .field-row').evaluateAll(rows=>rows.map(row=>{
  const label=row.querySelector('.field-label')!.getBoundingClientRect();
  const value=row.children[1].getBoundingClientRect();
  return {labelRight:label.right,valueLeft:value.left,gap:parseFloat(getComputedStyle(row).columnGap)};
 }));
 const longestLabelRight=Math.max(...columns.map(row=>row.labelRight));
 for(const row of columns)expect(row.valueLeft).toBeCloseTo(longestLabelRight+row.gap,0);
 const bounds=(await bar.boundingBox())!;const button=(await bar.getByRole('button',{name:'切换药品',exact:true}).boundingBox())!;
 expect(button.x+button.width).toBeLessThanOrEqual(bounds.x+bounds.width);
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth)).toBe(true);
});

test.describe('local medication presentation',()=>{
 test.use({timezoneId:'America/Los_Angeles'});
 test('period and clocks display local time without technical fields',async({page})=>{
  await setup(page);
  const plan={medication_id:'drug1',medication_plan_id:'plan1',member_id:'self',medication_identity:{generic_name:'测试药品'},time_status:'ongoing',starts_at:'2026-09-07T00:00:00+08:00',ends_at:'2026-09-10T00:00:00+08:00',start_precision:'date',end_precision:'date',timezone:'Asia/Shanghai',dose_text:'1 片',usage_status:'unknown',schedule:{kind:'daily',times:[{time:'08:00'}]}};
  await page.route('**/api/members/self/medication-plans**',route=>route.fulfill({json:new URL(route.request().url()).pathname.endsWith('/plan1')?plan:{items:[plan],next_cursor:null}}));
  await page.goto('/health/self/medications/plans/plan1');
  await expect(page.getByRole('button',{name:'开始日期',exact:true})).toHaveText('2026年9月6日');
  await expect(page.getByRole('button',{name:'结束日期',exact:true})).toHaveText('2026年9月9日');
  await expect(page.getByRole('button',{name:'用药时间',exact:true})).toContainText('17:00');
  const labels=await page.locator('.medication-plan-fields .field-label').allTextContents();
  expect(labels.filter(label=>['用药频率','用药时间','每次剂量','用药周期'].includes(label))).toEqual(['用药频率','用药时间','每次剂量','用药周期']);
  for(const label of ['时区','开始时间精度','结束时间精度','使用反馈','用药原因','时间说明','使用部位','使用说明','用法原文','变更原因'])await expect(page.getByLabel(label,{exact:true})).toHaveCount(0);
  await expect(page.getByRole('heading',{name:'计划说明',exact:true})).toHaveCount(0);
  await expect(page.locator('.medication-plan-fields').getByLabel('备注',{exact:true})).toBeVisible();
  await expect(page.getByRole('heading',{name:'备注',exact:true})).toHaveCount(0);
  await expect(page.getByRole('heading',{name:'站内用药提醒',exact:true})).toHaveCount(0);
  await expect(page.getByRole('button',{name:'查看用药提醒',exact:true})).toHaveCount(0);
  await expect(page.locator('.report-timeline-copy')).not.toContainText('未确认');
 });
});
test('multiple scheduled times share one dose field',async({page})=>{
 await setup(page);let saved:any;
 const plan={medication_id:'drug1',medication_plan_id:'plan1',member_id:'self',medication_identity:{generic_name:'剂量验收'},starts_at:'2026-09-07T00:00:00Z',ends_at:null,start_precision:'date',end_precision:null,timezone:'UTC',dose_text:'1 片',usage_status:'unknown',schedule:{kind:'daily',times:[{time:'08:00'},{time:'20:00'}]}};
 await page.route('**/api/members/self/medication-plans**',route=>{
  if(route.request().method()==='PATCH'){saved=route.request().postDataJSON();return route.fulfill({json:{...plan,...saved}});}
  return route.fulfill({json:new URL(route.request().url()).pathname.endsWith('/plan1')?plan:{items:[plan],next_cursor:null}});
 });
 await page.goto('/health/self/medications/plans/plan1');
 await expect(page.getByLabel('每次剂量',{exact:true})).toHaveValue('1 片');
 await expect(page.getByRole('button',{name:'分别设置剂量',exact:true})).toHaveCount(0);
 expect((await page.locator('.medication-plan-fields .field-label').allTextContents()).filter(label=>label.includes('剂量'))).toEqual(['每次剂量']);
 await page.getByLabel('每次剂量',{exact:true}).fill('3 片');
 await expect(page.getByRole('button',{name:'应用阶段调整',exact:true})).toHaveCount(0);
 await expect.poll(()=>saved?.dose_text).toBe('3 片');
 expect(saved).toEqual({dose_text:'3 片'});
});
test.describe('independent plan summaries',()=>{
 test.use({timezoneId:'UTC'});
 test('same medicine plans show only period frequency and time, with one autosaved arrangement',async({page})=>{
 await setup(page);let fail=true;
 const arrangement={starts_at:'2026-09-07T00:00:00Z',ends_at:'2026-09-11T00:00:00Z',start_precision:'date',end_precision:'date',timezone:'UTC',dose_text:'1 片',usage_status:'unknown',schedule:{kind:'daily',times:[{time:'08:00'}]}};
 let plan:any={medication_id:'drug1',medication_plan_id:'plan1',member_id:'self',time_status:'ongoing',medication_identity:{generic_name:'同一种药品'},...arrangement};
 const second={...plan,medication_plan_id:'plan2',...arrangement,ends_at:'long_term',end_precision:null,dose_text:'2 片',schedule:{kind:'daily',times:[{time:'20:00'}]}};
 await page.route('**/api/members/self/medication-plans**',route=>{
  if(route.request().method()==='PATCH'){
   if(fail)return route.fulfill({status:503,json:{detail:{message:'保存失败'}}});
   plan={...plan,...route.request().postDataJSON()};return route.fulfill({json:plan});
  }
  return route.fulfill({json:new URL(route.request().url()).pathname.endsWith('/plan1')?plan:{items:[plan,second],next_cursor:null}});
 });
 await page.goto('/health/self/medications/plans/plan1');
 const rows=page.locator('.report-timeline-item');await expect(rows).toHaveCount(2);
 await expect(rows.nth(0).locator('.content-description')).toHaveText('2026年9月7日 至 2026年9月10日 · 每日 · 08:00');
 await expect(rows.nth(1).locator('.content-description')).toHaveText('2026年9月7日 至 长期 · 每日 · 20:00');
 await expect(page.getByRole('heading',{name:'用药安排',exact:true})).toHaveCount(1);
 await expect(page.getByRole('heading',{name:/使用阶段/})).toHaveCount(0);
 await expect(page.getByRole('button',{name:/添加使用阶段|删除此阶段/})).toHaveCount(0);
 await page.getByLabel('每次剂量',{exact:true}).fill('3 片');await expect(page.getByRole('alert')).toContainText('保存失败');
 await page.getByRole('button',{name:'医疗报告',exact:true}).click();await expect(page).toHaveURL(/plans\/plan1$/);
 await expect(page.getByLabel('每次剂量',{exact:true})).toHaveValue('3 片');
 fail=false;await page.getByRole('button',{name:'重试保存',exact:true}).click();
 await expect.poll(()=>plan.dose_text).toBe('3 片');
 expect(second.dose_text).toBe('2 片');
 });
});
for(const [label,kind] of [['每隔若干日','every_n_days'],['按需','as_needed']])test(`date period supplies the schedule anchor for ${kind}`,async({page})=>{
 await setup(page);let submitted:any;
 await page.route('**/api/members/self/medication-plans**',route=>{
  if(route.request().method()==='POST'){submitted=route.request().postDataJSON();return route.fulfill({status:503,json:{detail:{message:'保留验收草稿'}}});}
  return route.fulfill({json:{items:[],next_cursor:null}});
 });
 await page.goto('/health/self/medications/plans');
 await page.getByRole('button',{name:'创建用药计划',exact:true}).click();
 const dialog=page.locator('.creation-dialog');
 await selectPlanDrug(page);
 await dialog.getByRole('button',{name:'开始日期',exact:true}).click();
 const picker=page.getByRole('dialog',{name:'开始日期选择器',exact:true});
 for(const [name,value] of [['年份','2026'],['月份','09'],['日期','07']])await picker.getByRole('textbox',{name,exact:true}).fill(value);
 await picker.getByRole('button',{name:'完成',exact:true}).click();
 await dialog.getByRole('button',{name:'用药频率',exact:true}).click();
 await expect(dialog.getByRole('group',{name:'选择用药频率'}).getByRole('button')).toHaveText(['未记录','按需','每日','每隔若干日','每周指定日']);
 await dialog.getByRole('button',{name:label,exact:true}).click();
 if(kind==='every_n_days')await dialog.getByLabel('间隔天数',{exact:true}).fill('2');
 await dialog.getByRole('button',{name:'返回上一级',exact:true}).click();
 if(kind==='every_n_days'){
  await dialog.getByRole('button',{name:'用药时间',exact:true}).click();
  await dialog.getByRole('button',{name:'添加用药时间',exact:true}).click();
  const timePicker=page.getByRole('dialog',{name:'添加用药时间',exact:true});
  await timePicker.getByRole('textbox',{name:'小时',exact:true}).fill('08');
  await timePicker.getByRole('textbox',{name:'分钟',exact:true}).fill('00');
  await timePicker.getByRole('button',{name:'完成',exact:true}).click();
  await dialog.getByRole('button',{name:'返回上一级',exact:true}).click();
 }
 await dialog.getByRole('button',{name:'完成',exact:true}).click();
 await expect.poll(()=>submitted).toBeTruthy();
 const phase=submitted;expect(phase.start_precision).toBe('date');expect(phase.ends_at).toBeNull();
 expect(phase.schedule.kind).toBe(kind);
 if(kind==='every_n_days'){expect(phase.schedule.anchor_date).toBe('2026-09-07');expect(phase.schedule.interval_days).toBe(2);}
 if(kind==='as_needed')expect(phase.schedule.times).toEqual([]);
});
test('plan status single select filters the three dated states',async({page})=>{
 await mockWorkspace(page);
 const queries:string[]=[];
 await page.route('**/api/members/self/medication-plans**',route=>{
   const status=new URL(route.request().url()).searchParams.get('status')||'';queries.push(status);
   return route.fulfill({json:{items:[],next_cursor:null}});
 });
 await page.goto('/health/self/medications/plans');
 const status=page.getByRole('button',{name:'用药计划状态',exact:true});
 const menu=page.getByRole('listbox',{name:'用药计划状态候选项',exact:true});
 await expect(status).toHaveText('进行中');
 await status.click();
 await expect(menu.getByRole('option')).toHaveText(['进行中','未开始','已结束']);
 await expect(menu.getByRole('option',{selected:true})).toHaveText('进行中');
 await page.keyboard.press('Escape');await expect(menu).toHaveCount(0);
 await expect(status).toBeFocused();
 await expect.poll(()=>queries.at(-1)).toBe('ongoing');
 for(const [label,value] of [['未开始','upcoming'],['已结束','ended']]){
  await status.click();await menu.getByRole('option',{name:label,exact:true}).click();await expect(menu).toHaveCount(0);await expect(status).toHaveText(label);await expect.poll(()=>queries.at(-1)).toBe(value);
 }
 await expect(page.getByRole('switch',{name:'仅日期未记录',exact:true})).toHaveCount(0);
 await status.click();await menu.getByRole('option',{name:'进行中',exact:true}).click();
 await expect.poll(()=>queries.at(-1)).toBe('ongoing');
 await expect(page.getByRole('tab',{name:'药品库存',exact:true})).toBeVisible();
});
test('medication identity fields save independently and preserve the other values',async({page})=>{
 const read=await setup(page);await openCatalogSettings(page);
 for(const name of ['通用名','商品名','浓度含量','包装规格'])await expect(page.getByRole('button',{name:'编辑'+name,exact:true})).toBeVisible();
 await page.getByRole('button',{name:'编辑商品名',exact:true}).click();
 await page.getByLabel('商品名',{exact:true}).fill('示例商品');
 await page.getByRole('button',{name:'编辑通用名',exact:true}).click();
 await page.getByLabel('通用名',{exact:true}).fill('示例滴眼液');
 await page.getByRole('button',{name:'编辑浓度含量',exact:true}).click();
 await expect.poll(()=>read().generic_name).toBe('示例滴眼液');
 await expect.poll(()=>read().brand_name).toBe('示例商品');
 expect(read()).not.toHaveProperty('name');
 await expect(page.locator('.dictionary-list-column')).toContainText('示例商品 示例滴眼液');
 await expect(page.locator('.medication-editor .report-basic-information')).toContainText('示例滴眼液');
 await expect(page.locator('.medication-editor .report-basic-information')).toContainText('示例商品');
 await page.getByLabel('浓度含量',{exact:true}).fill('0.1%');
 await page.getByRole('button',{name:'编辑包装规格',exact:true}).click();
 await page.getByLabel('包装规格',{exact:true}).fill('5 ml / 瓶，1 瓶 / 盒');
 await page.getByLabel('备注',{exact:true}).click();
 await expect.poll(()=>read().strength).toBe('0.1%');
 await expect(page.getByRole('button',{name:'编辑包装规格',exact:true})).toHaveText('5 ml / 瓶，1 瓶 / 盒');
 for(const name of ['药品分类','生产厂家','剂型','说明书标题','发布方','版本','读取时间'])await expect(page.getByLabel(name,{exact:true})).toHaveCount(0);
 await page.getByRole('button',{name:'编辑浓度含量',exact:true}).click();await page.getByLabel('浓度含量',{exact:true}).fill('');
 await expect.poll(()=>read().strength).toBeNull();
 await expect(page.getByRole('button',{name:'编辑包装规格',exact:true})).toHaveText('5 ml / 瓶，1 瓶 / 盒');
});
test('supplementary medication sources retry the whole batch and preview safely',async({page})=>{
 await setup(page);
 const files:any[]=[];const requests:string[]=[];let calls=0;
 const png=Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Wl6l5sAAAAASUVORK5CYII=','base64');
 await page.route('**/api/medication-catalog/drug1',route=>route.fulfill({json:{...medication,sources:files}}));
 await page.route('**/api/medication-catalog/drug1/source-files',route=>{
  requests.push(route.request().headers()['idempotency-key']);calls++;
  if(calls===1)return route.fulfill({status:503,json:{detail:{message:'整批保存失败'}}});
  files.push({resource_id:'image',original_filename:'药盒.png',mime_type:'image/png',purpose:'package',is_primary:1,source_index:0}, {resource_id:'text',original_filename:'标签.txt',mime_type:'text/plain',purpose:'label',is_primary:0,source_index:1});
  return route.fulfill({status:201,json:{...medication,sources:files}});
 });
 await page.route('**/api/medication-catalog/drug1/source-files/*',route=>route.fulfill({contentType:route.request().url().endsWith('/image')?'image/png':'text/plain',body:route.request().url().endsWith('/image')?png:Buffer.from('补充标签原文')}));
 await openCatalogSettings(page);
 await page.locator('.medication-overview input[type=file]').setInputFiles([{name:'药盒.png',mimeType:'image/png',buffer:png},{name:'标签.txt',mimeType:'text/plain',buffer:Buffer.from('补充标签原文')}]);
 await page.getByRole('button',{name:'重试上传（2）',exact:true}).click();
 await expect(page.getByRole('button',{name:'打开原件预览，共 2 个关联文件',exact:true})).toBeVisible();
 expect(requests).toHaveLength(2);expect(requests[0]).toBe(requests[1]);
 const image=page.locator('.original-file-thumbnail-frame img');await expect(image).toBeVisible();
 await page.getByRole('button',{name:'打开原件预览，共 2 个关联文件',exact:true}).click();
 const dialog=page.getByRole('dialog');await expect(dialog.getByRole('img',{name:'药盒.png',exact:true})).toBeVisible();
 await dialog.getByRole('button',{name:'查看关联文件：标签.txt',exact:true}).click();await expect(dialog.locator('pre')).toHaveText('补充标签原文');
 await page.keyboard.press('Escape');await expect(dialog).toHaveCount(0);
 await expect(page.getByRole('button',{name:'打开原件预览，共 2 个关联文件',exact:true})).toBeFocused();
});
test('medicine and plan creation expose no report association',async({page})=>{
 await setup(page);await page.goto('/health/self/medications/catalog/drug1');
 await expect(page.locator('.medication-editor')).toContainText('示例药品');
 await expect(page.getByRole('button',{name:'添加关联医疗报告',exact:true})).toHaveCount(0);
 await expect(page.getByRole('heading',{name:'用药依据（可选）',exact:true})).toHaveCount(0);
 await page.route('**/api/members/self/medication-plans**',route=>route.fulfill({json:{items:[],next_cursor:null}}));
 await page.getByRole('tab',{name:'用药计划',exact:true}).click();
 await page.getByRole('button',{name:'创建用药计划',exact:true}).click();
 await expect(page.getByRole('heading',{name:'用药依据（可选）',exact:true})).toHaveCount(0);
 await expect(page.getByRole('button',{name:'添加关联医疗报告',exact:true})).toHaveCount(0);
});

for(const width of [1280,390])for(const section of ['catalog','plans'] as const)test(`${section} create action floats above short and long lists at ${width}px`,async({page})=>{
 await setup(page);await page.setViewportSize({width,height:900});
 const resource=section==='catalog'?'medications':'medication-plans';
 await page.route(`**/api/members/self/${resource}**`,route=>{
  const count=new URL(route.request().url()).searchParams.get('query')?36:1;
  const items=Array.from({length:count},(_,i)=>section==='catalog'?{...medication,medication_id:`drug${i}`,generic_name:`药品 ${i}`}:{medication_id:'drug1',medication_plan_id:`plan${i}`,medication_identity:{generic_name:`药品 ${i}`},time_status:'ongoing',usage_status:'active',starts_at:null});
  return route.fulfill({json:{items,next_cursor:null}});
 });
 await page.goto(`/health/self/medications/${section}`);
 const pane=page.getByRole('region',{name:'用药记录列表',exact:true});
 const rows=pane.locator('.report-timeline-item');await expect(rows).toHaveCount(1);
 const action=page.getByRole('button',{name:section==='catalog'?'添加药品批次':'创建用药计划',exact:true});
 const original=(await action.boundingBox())!;const bounds=(await pane.boundingBox())!;
 expect(bounds.y+bounds.height-original.y-original.height).toBeCloseTo(15,0);
 expect(original.x).toBeGreaterThanOrEqual(bounds.x);expect(original.x+original.width).toBeLessThanOrEqual(bounds.x+bounds.width);
 if(section==='plans')await page.getByRole('button',{name:'展开搜索栏',exact:true}).click();
 await page.getByRole('searchbox',{name:'搜索用药资料',exact:true}).fill('药品');await expect(rows).toHaveCount(36);
 await pane.locator('.report-library-scroll').evaluate(element=>{element.scrollTop=element.scrollHeight;});
 await expect.poll(async()=>(await action.boundingBox())!.y).toBeCloseTo(original.y,0);
 await expect(rows.last()).toBeInViewport();
 const last=(await rows.last().boundingBox())!;expect(last.y+last.height).toBeLessThan(original.y);
 await expect(page.getByRole('button',{name:'拍照或上传识别',exact:true})).toHaveCount(0);
 if(section==='catalog'){
  await action.click();const dialog=page.locator('.creation-dialog');
  await expect(dialog.getByRole('button',{name:'选择药品：未选择',exact:true})).toBeVisible();
  await expect(dialog.locator('input[type=file]')).toHaveCount(0);
  await page.keyboard.press('Escape');await expect(dialog).toHaveCount(0);await expect(action).toBeFocused();
 }
});

for(const width of [1280,390])test(`medicine identity and single original use a compact report layout at ${width}px`,async({page})=>{
 await setup(page);await page.setViewportSize({width,height:900});
 const file={resource_id:'text',original_filename:'药品说明.txt',mime_type:'text/plain',purpose:'label'};
 let fail=true;
 await page.route('**/api/members/self/medications/drug1',route=>route.fulfill({json:{...medication,brand_name:'示例商品',generic_name:'示例滴眼液',leaflet_url:'https://example.test/leaflet',sources:[file]}}));
 await page.route('**/api/members/self/medications/drug1/source-files/text',route=>{
  if(fail){fail=false;return route.fulfill({status:503,json:{detail:{message:'文件暂时无法读取'}}});}
  return route.fulfill({contentType:'text/plain',body:'说明书原件内容'});
 });
 await page.goto('/health/self/medications/catalog/drug1');
 await expect(page.locator('.medication-editor .report-basic-information')).toContainText('示例滴眼液');
 await expect(page.locator('.medication-editor .report-basic-information')).toContainText('示例商品');
 const leaflet=page.getByRole('link',{name:'查看说明书',exact:true});
 await expect(leaflet).toBeVisible();
 expect(await leaflet.evaluate(element=>parseFloat(getComputedStyle(element).borderTopLeftRadius))).toBe(0);
 expect(await leaflet.evaluate(element=>element.parentElement?.classList.contains('grouped-object-list'))).toBe(true);
 expect(await leaflet.evaluate(element=>getComputedStyle(element).textDecorationLine)).toBe('none');
 expect(await leaflet.evaluate(element=>Boolean(element.closest('.grouped-object-list')))).toBe(true);
 await expect(page.locator('.medication-editor textarea')).toHaveCount(0);
 await expect(page.getByRole('heading',{name:'备注',exact:true})).toHaveCount(0);
 const thumbnail=page.getByRole('button',{name:'打开原件预览，共 1 个关联文件',exact:true});
 await expect(page.getByRole('button',{name:/查看文件（/})).toHaveCount(0);
 await thumbnail.click();const dialog=page.getByRole('dialog',{name:file.original_filename,exact:true});
 await expect(dialog.getByRole('alert')).toContainText('文件暂时无法读取');
 await dialog.getByRole('button',{name:'重试',exact:true}).click();
 await expect(dialog.locator('pre')).toHaveText('说明书原件内容');
 await expect(dialog.locator('.file-preview-files')).toHaveCount(0);
 const bounds=(await dialog.boundingBox())!;expect(bounds.x).toBeGreaterThanOrEqual(0);expect(bounds.x+bounds.width).toBeLessThanOrEqual(width);
 await page.keyboard.press('Escape');await expect(dialog).toHaveCount(0);await expect(thumbnail).toBeFocused();
 await thumbnail.click();await expect(dialog.locator('pre')).toHaveText('说明书原件内容');
 await expect(dialog.getByRole('button',{name:`删除原件 ${file.original_filename}`,exact:true})).toHaveCount(0);
 await page.keyboard.press('Escape');await expect(thumbnail).toBeVisible();
});

for(const width of [1280,390])test(`medicine fields use shared row hover and report original alignment at ${width}px`,async({page})=>{
 await setup(page);await page.setViewportSize({width,height:900});await openCatalogSettings(page);
 const info=page.locator('.medication-overview .report-basic-information');
 const originals=page.getByRole('region',{name:'药品图片与文件',exact:true});
 await expect(info).toBeVisible();await expect(originals).toBeVisible();
 const infoBox=(await info.boundingBox())!;const fileBox=(await originals.boundingBox())!;
 if(width>650){
  expect(fileBox.y).toBeCloseTo(infoBox.y,0);
  expect(fileBox.y+fileBox.height).toBeCloseTo(infoBox.y+infoBox.height,0);
  expect(fileBox.x).toBeGreaterThan(infoBox.x+infoBox.width);
 }else{
  expect(fileBox.y+fileBox.height).toBeLessThan(infoBox.y);
  expect(fileBox.x).toBeCloseTo(infoBox.x,0);
  expect(fileBox.width).toBeCloseTo(infoBox.width,0);
 }
 for(const label of ['通用名','商品名','浓度含量','包装规格']){
  const trigger=page.getByRole('button',{name:'编辑'+label,exact:true});
  const row=trigger.locator('xpath=ancestor::div[contains(@class,"field-row")]');
  await row.locator('.field-label').hover();
  const rowColor=await row.evaluate(async element=>{getComputedStyle(element).backgroundColor;await Promise.all(element.getAnimations().map(animation=>animation.finished));return getComputedStyle(element).backgroundColor;});
  await trigger.hover();
  await expect.poll(()=>row.evaluate(element=>getComputedStyle(element).backgroundColor)).toBe(rowColor);
  expect(rowColor).not.toBe('rgba(0, 0, 0, 0)');
  expect(await trigger.evaluate(element=>getComputedStyle(element).backgroundColor)).toBe('rgba(0, 0, 0, 0)');
 }
 await page.getByRole('button',{name:'编辑商品名',exact:true}).click();
 await expect(page.getByLabel('商品名',{exact:true})).toBeFocused();
});


for (const width of [1280, 390]) test(`compact date picker persists long-term and unknown at ${width}px`, async ({page}, testInfo) => {
 await setup(page);
 await page.setViewportSize({width, height: 844});
 await page.clock.setFixedTime(new Date('2026-09-08T12:05:00'));
 let saved: any = {medication_id:'drug1',medication_plan_id:'date-plan', member_id:'self', medication_identity:{generic_name:'日期验收药品'}, starts_at:'2026-09-01T00:00:00Z',ends_at:'2026-09-12T00:00:00Z',start_precision:'date',end_precision:'date',timezone:'UTC',usage_status:'unknown',schedule:null};
 await page.route('**/api/members/self/medication-plans**', route => {
  if (route.request().method() === 'PATCH') saved = {...saved, ...route.request().postDataJSON()};
  return route.fulfill({json:new URL(route.request().url()).pathname.endsWith('/date-plan') ? saved : {items:[saved],next_cursor:null}});
 });
 await page.goto('/health/self/medications/plans/date-plan');
 const trigger = page.getByRole('button', {name:'结束日期',exact:true});
 const picker = page.getByRole('dialog', {name:'结束日期选择器',exact:true});
 await trigger.click();
 for (const name of ['今天','长期','未知']) await expect(picker.getByRole('button',{name,exact:true})).toBeVisible();
 await expect(picker.getByRole('textbox',{name:'年份',exact:true})).toHaveCSS('font-size','13px');
 await expect(picker.getByRole('textbox',{name:'年份',exact:true})).toHaveCSS('height','30px');
 await expect(picker.getByRole('gridcell').first()).toHaveCSS('font-size','13px');
 await expect(picker.getByRole('gridcell').first()).toHaveCSS('height','30px');
 await expect(picker.getByRole('button',{name:'今天',exact:true})).toHaveCSS('font-size','13px');
 const rect = (await picker.boundingBox())!;
 expect(rect.x).toBeGreaterThanOrEqual(15);
 expect(rect.x + rect.width).toBeLessThanOrEqual(width - 15);
 expect(await picker.evaluate(el => el.scrollWidth - el.clientWidth)).toBeLessThanOrEqual(1);
 await picker.screenshot({path:testInfo.outputPath(`compact-date-picker-${width}.png`)});
 await picker.getByRole('button',{name:'长期',exact:true}).click();
 await expect(picker).toHaveCount(0);
 await expect.poll(() => saved.ends_at).toBe('long_term');
 expect(saved.end_precision).toBeNull();
 await page.reload();
 await expect(trigger).toHaveText('长期');
 await trigger.click();
 await expect(picker.getByRole('button',{name:'长期',exact:true})).toHaveAttribute('aria-pressed','true');
 await expect(picker.locator('[aria-selected="true"]')).toHaveCount(0);
 await picker.getByRole('button',{name:'未知',exact:true}).click();
 await expect.poll(() => saved.ends_at).toBeNull();
 await page.reload();
 await expect(trigger).toHaveText('未知');
 await trigger.click();
 await picker.getByRole('button',{name:'今天',exact:true}).click();
 await expect(picker.getByRole('textbox',{name:'日期',exact:true})).toHaveValue('08');
 await picker.getByRole('button',{name:'完成',exact:true}).click();
 await expect.poll(() => saved.end_precision).toBe('date');
 await expect(trigger).toHaveText('2026年9月8日');
 await page.getByRole('button',{name:'开始日期',exact:true}).click();
 const required = page.getByRole('dialog',{name:'开始日期选择器',exact:true});
 await expect(required.getByRole('button',{name:'长期',exact:true})).toHaveCount(0);
 await expect(required.getByRole('button',{name:'未知',exact:true})).toHaveCount(0);
 await required.getByRole('button',{name:'取消',exact:true}).click();
});

test.describe('schedule settings with fixed timezone',()=>{
 test.use({timezoneId:'UTC'});
for(const width of [1280,390])test(`schedule settings follow shared design and never trap incomplete selections at ${width}px`,async({page},testInfo)=>{
 await setup(page);await page.setViewportSize({width,height:900});
 let fail=false;
 let plan:any={medication_id:'drug1',medication_plan_id:'settings-plan',member_id:'self',medication_identity:{generic_name:'设置验收药品'},starts_at:'2026-09-07T00:00:00Z',ends_at:null,start_precision:'date',end_precision:null,timezone:'UTC',usage_status:'unknown',schedule:{kind:'daily',times:[{time:'08:00'},{time:'20:00'}]}};
 await page.route('**/api/members/self/medication-plans**',route=>{
  if(route.request().method()==='PATCH'){
   if(fail)return route.fulfill({status:503,json:{detail:{message:'保存暂时失败'}}});
   plan={...plan,...route.request().postDataJSON()};
  }
  return route.fulfill({json:new URL(route.request().url()).pathname.endsWith('/settings-plan')?plan:{items:[plan],next_cursor:null}});
 });
 await page.goto('/health/self/medications/plans/settings-plan');
 const frequency=page.getByRole('button',{name:'用药频率',exact:true});const times=page.getByRole('button',{name:'用药时间',exact:true});
 await frequency.click();
 const screen=page.getByRole('region',{name:'用药频率设置',exact:true});
 await expect(screen.getByRole('button',{name:'完成',exact:true})).toHaveCount(0);
 await screen.getByRole('button',{name:'每隔若干日',exact:true}).click();
 await expect(screen.getByRole('alert')).toContainText('间隔天数');
 await page.locator('.medication-detail > .workspace-navigation-toolbar').getByRole('button',{name:'返回上一级',exact:true}).click();
 await expect(frequency).toContainText('每日');
 await frequency.click();await expect(screen.getByLabel('间隔天数',{exact:true})).toHaveValue('');
 await screen.getByLabel('间隔天数',{exact:true}).fill('2');
 await expect.poll(()=>plan.schedule.interval_days).toBe(2);
 for(const group of await screen.locator('.grouped-object-list').all())await expect(group).toHaveCSS('border-radius','10px');
 await screen.screenshot({path:testInfo.outputPath(`frequency-${width}.png`)});
 await page.locator('.medication-detail > .workspace-navigation-toolbar').getByRole('button',{name:'返回上一级',exact:true}).click();
 await times.click();
 const timeScreen=page.getByRole('region',{name:'用药时间设置',exact:true});
 await expect(timeScreen.getByRole('button',{name:'完成',exact:true})).toHaveCount(0);
 await expect(timeScreen.locator('input[type=time]')).toHaveCount(0);
 await expect(timeScreen.locator('.content-description')).toHaveCount(0);
 await expect(timeScreen.locator('.grouped-object-list > *').first()).toContainText('添加用药时间');
 const add=timeScreen.getByRole('button',{name:'添加用药时间',exact:true});
 const picker=page.getByRole('dialog',{name:'添加用药时间',exact:true});
 await add.click();
 await expect(picker.getByRole('grid')).toHaveCount(0);
 await expect(picker.getByRole('textbox',{name:'小时',exact:true})).toHaveCSS('font-size','13px');
 await picker.getByRole('textbox',{name:'小时',exact:true}).fill('');
 await expect(picker.getByRole('button',{name:'完成',exact:true})).toBeDisabled();
 await page.keyboard.press('Escape');await expect(picker).toHaveCount(0);await expect(timeScreen).toBeVisible();
 expect(plan.schedule.times).toHaveLength(2);
 await add.click();await picker.getByRole('textbox',{name:'小时',exact:true}).fill('12');await expect(picker.getByRole('textbox',{name:'小时',exact:true})).toHaveValue('12');await picker.getByRole('textbox',{name:'分钟',exact:true}).fill('30');await expect(picker.getByRole('textbox',{name:'小时',exact:true})).toHaveValue('12');
 await picker.getByRole('button',{name:'完成',exact:true}).click();
 await expect.poll(()=>plan.schedule.times.length).toBe(3);
 await add.click();await picker.getByRole('textbox',{name:'小时',exact:true}).fill('12');await expect(picker.getByRole('textbox',{name:'小时',exact:true})).toHaveValue('12');await picker.getByRole('textbox',{name:'分钟',exact:true}).fill('30');await expect(picker.getByRole('textbox',{name:'小时',exact:true})).toHaveValue('12');
 await picker.getByRole('button',{name:'完成',exact:true}).click();await expect(picker.getByRole('alert')).toContainText('此时间已添加');
 await picker.screenshot({path:testInfo.outputPath(`time-picker-${width}.png`)});
 await picker.getByRole('button',{name:'关闭添加用药时间',exact:true}).click();await expect(picker).toHaveCount(0);
 await expect(timeScreen.getByRole('button',{name:'时间 4',exact:true})).toHaveCount(0);
 fail=true;await timeScreen.getByRole('button',{name:'时间 3',exact:true}).click({button:'right'});await page.getByRole('menuitem',{name:'删除',exact:true}).click();
 await expect(timeScreen.getByRole('alert')).toContainText('保存暂时失败');
 fail=false;await timeScreen.getByRole('button',{name:'重试保存',exact:true}).click();
 await expect.poll(()=>plan.schedule.times.length).toBe(2);
 await timeScreen.screenshot({path:testInfo.outputPath(`times-${width}.png`)});
 await page.keyboard.press('Escape');await expect(times).toContainText('08:00、20:00');
 await frequency.click();await screen.getByRole('button',{name:'每周指定日',exact:true}).click();
 await expect(screen.getByRole('alert')).toContainText('用药星期');
 if(width===390){
  await page.locator('.medication-detail > .workspace-navigation-toolbar').getByRole('button',{name:'返回上一级',exact:true}).click();
  await page.getByRole('region',{name:'用药详情',exact:true}).getByRole('button',{name:'返回上一级',exact:true}).click();
  await page.getByRole('button',{name:'身体指标',exact:true}).click();
  await expect(page).toHaveURL(/\/body-metrics$/);
 }else{
  await page.getByRole('button',{name:'发起新聊天',exact:true}).click();
  await expect(page.locator('.conversation-composer textarea')).toBeVisible();
 }
 await page.goto('/health/self/medications/plans/settings-plan');
 await expect(times).toContainText('08:00、20:00');await expect(frequency).toContainText('每隔 2 日');
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
});

});

for(const width of [1280,390])test(`frequency selected rows keep all four corners after pointer leaves at ${width}px`,async({page},testInfo)=>{
 await setup(page);await page.setViewportSize({width,height:900});
 const plan={medication_id:'drug1',medication_plan_id:'corners',member_id:'self',medication_identity:{generic_name:'圆角验收药品'},starts_at:'2026-09-04T00:00:00Z',start_precision:'date',timezone:'UTC',schedule:{kind:'daily',times:[]}};
 await page.route('**/api/members/self/medication-plans**',route=>route.fulfill({json:new URL(route.request().url()).pathname.endsWith('/corners')?{...plan,...(route.request().method()==='PATCH'?route.request().postDataJSON():{})}:{items:[plan],next_cursor:null}}));
 await page.goto('/health/self/medications/plans/corners');await page.getByRole('button',{name:'用药频率',exact:true}).click();
 const screen=page.getByRole('region',{name:'用药频率设置',exact:true});
 for(const name of ['未记录','每隔若干日','每周指定日']){
  const selected=screen.getByRole('button',{name,exact:true});await selected.click();await page.locator('.medication-detail > .workspace-navigation-toolbar').getByRole('heading',{name:'用药频率',exact:true}).hover();
  await expect(selected).toHaveAttribute('aria-pressed','true');
  for(const corner of ['top-left','top-right','bottom-left','bottom-right'])await expect(selected).toHaveCSS(`border-${corner}-radius`,'10px');
  expect(await selected.evaluate(element=>getComputedStyle(element,'::before').opacity)).toBe('0');
  if(await selected.evaluate(element=>Boolean(element.nextElementSibling)))expect(await selected.evaluate(element=>getComputedStyle(element.nextElementSibling!,'::before').opacity)).toBe('0');
  if(name==='每隔若干日'){
   await screen.getByRole('button',{name:'每日',exact:true}).hover();
   for(const corner of ['top-left','top-right','bottom-left','bottom-right'])await expect(selected).toHaveCSS(`border-${corner}-radius`,'10px');
   await screen.screenshot({path:testInfo.outputPath(`frequency-selected-${width}.png`)});
  }
 }
});

for(const width of [1280,390])test(`weekdays use left checkboxes and autosave multiple selections at ${width}px`,async({page},testInfo)=>{
 await setup(page);await page.setViewportSize({width,height:900});
 let plan:any={medication_id:'drug1',medication_plan_id:'weekdays',member_id:'self',medication_identity:{generic_name:'星期验收药品'},starts_at:'2026-09-04T00:00:00Z',start_precision:'date',timezone:'UTC',schedule:{kind:'daily',times:[{time:'08:00'}]}};
 await page.route('**/api/members/self/medication-plans**',route=>{
  if(route.request().method()==='PATCH')plan={...plan,...route.request().postDataJSON()};
  return route.fulfill({json:new URL(route.request().url()).pathname.endsWith('/weekdays')?plan:{items:[plan],next_cursor:null}});
 });
 await page.goto('/health/self/medications/plans/weekdays');await page.getByRole('button',{name:'用药频率',exact:true}).click();
 await page.getByRole('button',{name:'每周指定日',exact:true}).click();
 const days=page.getByRole('group',{name:'用药星期',exact:true});
 await expect(days.getByRole('switch')).toHaveCount(0);await expect(days.getByRole('checkbox')).toHaveCount(7);
 const monday=days.getByRole('checkbox',{name:'星期一',exact:true}),wednesday=days.getByRole('checkbox',{name:'星期三',exact:true});
 await monday.focus();await monday.press('Space');await wednesday.click();await expect(monday).toBeChecked();await expect(wednesday).toBeChecked();
 await expect.poll(()=>plan.schedule.weekdays).toEqual([1,3]);
 await page.getByRole('heading',{name:'用药频率',exact:true}).click();
 const check=(await wednesday.locator('.selection-check-control').boundingBox())!,label=(await wednesday.locator('span').last().boundingBox())!;
 expect(check.x+check.width).toBeLessThan(label.x);
 expect(await wednesday.evaluate(element=>getComputedStyle(element).backgroundColor)).toBe(await days.getByRole('checkbox',{name:'星期二',exact:true}).evaluate(element=>getComputedStyle(element).backgroundColor));
 await page.getByRole('region',{name:'用药频率设置',exact:true}).screenshot({path:testInfo.outputPath(`weekdays-${width}.png`)});
 await monday.press('Space');await expect(monday).not.toBeChecked();await expect.poll(()=>plan.schedule.weekdays).toEqual([3]);
 await page.getByRole('button',{name:'返回上一级',exact:true}).click();await expect(page.getByRole('button',{name:'用药频率',exact:true})).toContainText('每周三');
 await page.reload();await page.getByRole('button',{name:'用药频率',exact:true}).click();await expect(wednesday).toBeChecked();await expect(monday).not.toBeChecked();
});

async function openCatalogSettings(page:Parameters<typeof mockWorkspace>[0]){await page.goto('/setting');await page.getByRole('complementary',{name:'设置导航'}).getByRole('button',{name:'药品目录',exact:true}).click();await page.locator('.dictionary-list-column .dictionary-entity-row').first().click();}
