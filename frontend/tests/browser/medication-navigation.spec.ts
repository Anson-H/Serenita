import {expect,test} from '@playwright/test';
import {mockWorkspace} from '../helpers/workspace';

const medicines=Array.from({length:4},(_,i)=>({medication_id:`drug${i}`,member_id:'self',generic_name:`库存药品${i}`,prescription_type:'unknown',notes:null,sources:[],batches:[]}));
const plans=Array.from({length:2},(_,i)=>({medication_plan_id:`plan${i}`,member_id:'self',medication_id:'drug0',medication_identity:{generic_name:`独立计划${i}`},time_status:'ongoing',notes:null,starts_at:'2026-09-01T00:00:00+08:00',ends_at:null,start_precision:'date',end_precision:null,timezone:'Asia/Shanghai',dose_text:'1 片',usage_status:'unknown',schedule:{kind:'daily',times:[{time:'08:00'}]}}));

for(const width of [1280,390])test(`repeated medication tabs preserve only their own rows and filters at ${width}px`,async({page})=>{
 await mockWorkspace(page);await page.setViewportSize({width,height:900});
 const errors:string[]=[];page.on('console',m=>{if(m.type()==='error')errors.push(m.text());});
 const planFilters:string[]=[];
 await page.route('**/api/members/self/medications**',route=>{
  const url=new URL(route.request().url());const id=url.pathname.split('/').pop();
  const item=medicines.find(m=>m.medication_id===id);
  const query=url.searchParams.get('query')||'';
  return route.fulfill({json:item??{items:medicines.filter(m=>m.generic_name.includes(query)),next_cursor:null}});
 });
 await page.route('**/api/members/self/medication-plans**',route=>{
  const url=new URL(route.request().url());const item=plans.find(p=>url.pathname.endsWith('/'+p.medication_plan_id));
  if(!item)planFilters.push(url.searchParams.get('status')||'');
  return route.fulfill({json:item??{items:plans,next_cursor:null}});
 });
 await page.goto('/health/self/medications/catalog');
 const rows=page.locator('.report-timeline-item');
 await expect(rows).toHaveCount(4);
 for(let round=0;round<3;round++){
  await page.getByRole('tab',{name:'用药计划',exact:true}).click();
  await expect(rows).toHaveCount(2);await expect(rows.nth(0)).toContainText('独立计划0');
  for(const plan of plans){
   await page.getByRole('button',{name:new RegExp(plan.medication_identity.generic_name)}).click();
   await expect(page).toHaveURL(new RegExp('/plans/'+plan.medication_plan_id+'$'));
   await expect(page.getByRole('region',{name:'计划药品',exact:true})).toContainText(plan.medication_identity.generic_name);
   await expect(page.locator('.medication-detail .workspace-navigation-toolbar')).toHaveCount(1);
   await page.locator('.medication-detail').getByRole('button',{name:'返回上一级',exact:true}).click();
   await expect(page).toHaveURL(/\/plans$/);
  }
  await page.getByRole('tab',{name:'药品库存',exact:true}).click();await expect(rows).toHaveCount(4);
  await expect(rows.nth(3)).toContainText('库存药品3');
 }
 await page.getByRole('searchbox',{name:'搜索用药资料',exact:true}).fill('库存药品2');await expect(rows).toHaveCount(1);
 await page.getByRole('tab',{name:'用药计划',exact:true}).click();await expect(rows).toHaveCount(2);
 await page.getByRole('tab',{name:'药品库存',exact:true}).click();await expect(rows).toHaveCount(1);
 await expect(page.getByRole('searchbox',{name:'搜索用药资料',exact:true})).toHaveValue('库存药品2');
 expect(planFilters.every(value=>value==='ongoing')).toBe(true);
 expect(errors.filter(value=>/same key|unique.*key|Encountered two children/.test(value))).toEqual([]);
});

test('late pagination and failed catalog requests cannot contaminate another medication tab',async({page})=>{
 await mockWorkspace(page);let release!:()=>void;const gate=new Promise<void>(resolve=>{release=resolve;});let moreStarted=false;
 await page.route('**/api/members/self/medications**',async route=>{
  if(new URL(route.request().url()).searchParams.has('cursor')){moreStarted=true;await gate;await route.fulfill({json:{items:medicines.slice(2),next_cursor:null}});return;}
  await route.fulfill({json:{items:medicines.slice(0,2),next_cursor:'next'}});
 });
 let fail=false;
 await page.route('**/api/members/self/medication-plans**',route=>fail?route.fulfill({status:503,json:{detail:{message:'目录读取失败'}}}):route.fulfill({json:{items:plans,next_cursor:null}}));
 await page.goto('/health/self/medications/catalog');await expect(page.locator('.report-timeline-item')).toHaveCount(2);
 await page.getByRole('button',{name:'加载更多',exact:true}).click();await expect.poll(()=>moreStarted).toBe(true);
 await page.getByRole('tab',{name:'用药计划',exact:true}).click();await expect(page.locator('.report-timeline-item')).toHaveCount(2);
 release();
 await expect(page.locator('.report-timeline-item').first()).toContainText('独立计划0');
 await expect(page.getByRole('button',{name:'加载更多',exact:true})).toHaveCount(0);
 fail=true;await page.getByRole('button',{name:'展开搜索栏',exact:true}).click();await page.getByRole('searchbox',{name:'搜索用药资料',exact:true}).fill('不存在');
 await expect(page.getByRole('alert')).toContainText('目录读取失败');await expect(page.locator('.report-timeline-item')).toHaveCount(0);
 fail=false;await page.getByRole('button',{name:'重试',exact:true}).click();await expect(page.locator('.report-timeline-item')).toHaveCount(2);
});

test('read-only permission changes stop retries without trapping an unsaved editor',async({page})=>{
 await mockWorkspace(page);let editable=true;let writes=0;
 await page.route('**/api/members',route=>route.fulfill({json:{access_revision:editable?1:2,default_member_id:'self',initial_member_id:'self',last_member_id:'self',startup_mode:'last_used',members:[{member_id:'self',member_name:'共享成员',account_id:'owner',owner_account:'owner',is_owned:false,can_edit:editable,permission:editable?'edit':'read'}]}}));
 await page.route('**/api/members/self/medication-plans**',route=>{
  if(route.request().method()==='PATCH'){writes++;return route.fulfill({status:403,json:{detail:{message:'没有编辑权限'}}});}
  return route.fulfill({json:new URL(route.request().url()).pathname.endsWith('/plan0')?{...plans[0],starts_at:'2026-09-01T00:00:00Z',start_precision:'date',timezone:'UTC',notes:null}:{items:plans,next_cursor:null}});
 });
 await page.goto('/health/self/medications/plans/plan0');
 await page.getByLabel('备注',{exact:true}).fill('尚未保存的草稿');await expect(page.getByRole('alert')).toContainText('没有编辑权限');
 editable=false;await page.evaluate(()=>window.dispatchEvent(new Event('serenita:member-access-changed')));
 await expect(page.getByRole('button',{name:'删除用药计划',exact:true})).toHaveCount(0);
 const failedWrites=writes;
 await page.getByRole('tab',{name:'用药计划',exact:true}).click();await expect(page).toHaveURL(/\/plans$/);
 await expect(page.locator('.report-timeline-item')).toHaveCount(2);
 expect(writes).toBe(failedWrites);
});

test('changing members discards the old list response and uses the new member identifiers',async({page})=>{
 await mockWorkspace(page);let release!:()=>void;const gate=new Promise<void>(resolve=>{release=resolve;});let requested=false;
 await page.route('**/api/members',route=>route.fulfill({json:{access_revision:1,default_member_id:'self',initial_member_id:'self',last_member_id:'self',startup_mode:'last_used',members:['self','other'].map(member_id=>({member_id,member_name:member_id,account_id:'test',owner_account:'test',is_owned:true,can_edit:true,permission:'owner'}))}}));
 await page.route('**/api/members/self/medications**',async route=>{requested=true;await gate;await route.fulfill({json:{items:medicines,next_cursor:null}});});
 const other={...medicines[0],member_id:'other',medication_id:'other-drug',generic_name:'另一成员的药品'};
 await page.route('**/api/members/other/medications**',route=>route.fulfill({json:new URL(route.request().url()).pathname.endsWith('/other-drug')?other:{items:[other],next_cursor:null}}));
 await page.goto('/health/self/medications/catalog');await expect.poll(()=>requested).toBe(true);
 await page.evaluate(()=>{window.history.pushState(null,'','/health/other/medications/catalog');window.dispatchEvent(new PopStateEvent('popstate'));});
 await expect(page.locator('.report-timeline-item')).toHaveCount(1);release();
 await page.getByRole('button',{name:'另一成员的药品 规格未记录',exact:true}).click();await expect(page).toHaveURL(/other\/medications\/catalog\/other-drug$/);
 await expect(page.locator('.medication-overview')).toContainText('另一成员的药品');await expect(page.locator('.report-timeline-item')).toHaveCount(1);
});

for(const width of [1280,390])test(`schedule return restores the plan frame and scroll at ${width}px`,async({page},testInfo)=>{
 await mockWorkspace(page);await page.setViewportSize({width,height:600});
 const plan={...plans[0],notes:'用于检查返回设置页后的布局。'.repeat(25)};
 await page.route('**/api/members/self/medication-plans**',route=>route.fulfill({json:new URL(route.request().url()).pathname.endsWith('/plan0')?plan:{items:[plan],next_cursor:null}}));
 await page.goto('/health/self/medications/plans/plan0');
 const detail=page.locator('.medication-detail');const scroll=detail.locator(':scope > .report-detail-scroll');
 const toolbar=detail.locator(':scope > .workspace-navigation-toolbar');
 await expect(page.getByRole('button',{name:'用药频率',exact:true})).toBeVisible();
 const frame=()=>scroll.evaluate(element=>({padding:getComputedStyle(element).padding,gridRow:getComputedStyle(element).gridRow,scroll:element.scrollTop}));
 const initial=await frame();
 for(const label of ['用药频率','用药时间','用药频率','用药时间']){
  await scroll.evaluate(element=>element.scrollTop=30);
  const before=await frame();
  await page.getByRole('button',{name:label,exact:true}).click();
  const settings=page.getByRole('region',{name:label+'设置',exact:true});
  await expect(settings).toBeVisible();
  await expect(toolbar.locator('.workspace-navigation-title')).toHaveText(label);
  await toolbar.getByRole('button',{name:'返回上一级',exact:true}).click();
  await expect(settings).toHaveCount(0);
  await expect(toolbar).toBeVisible();
  await expect.poll(async()=>(await frame()).padding).toBe(initial.padding);
  await expect.poll(async()=>(await frame()).gridRow).toBe(initial.gridRow);
  await expect.poll(async()=>(await frame()).scroll).toBe(before.scroll);
  expect((await toolbar.boundingBox())!.y).toBeCloseTo((await detail.boundingBox())!.y,0);
 }
 await detail.screenshot({path:testInfo.outputPath(`schedule-return-${width}.png`)});
});

test('a new login generation discards cached medication filters including the outgoing page cleanup',async({page})=>{
 await mockWorkspace(page);
 await page.route('**/api/members/self/medications**',route=>{
  const query=new URL(route.request().url()).searchParams.get('query')||'';
  return route.fulfill({json:{items:medicines.filter(item=>item.generic_name.includes(query)),next_cursor:null}});
 });
 await page.route('**/api/members/self/medication-plans**',route=>route.fulfill({json:{items:plans,next_cursor:null}}));
 await page.goto('/health/self/medications/catalog');
 await page.getByRole('searchbox',{name:'搜索用药资料',exact:true}).fill('库存药品2');await expect(page.locator('.report-timeline-item')).toHaveCount(1);
 await page.evaluate(async()=>{const modulePath='/src/api/authLifecycle.ts';const auth=await import(/* @vite-ignore */ modulePath);auth.advanceAuthLifecycle('test');});
 await page.getByRole('tab',{name:'用药计划',exact:true}).click();await expect(page.locator('.report-timeline-item')).toHaveCount(2);
 await page.getByRole('tab',{name:'药品库存',exact:true}).click();await expect(page.locator('.report-timeline-item')).toHaveCount(4);
 await expect(page.getByRole('searchbox',{name:'搜索用药资料',exact:true})).toHaveValue('');
});

test('deleting the open plan uses its own identity and discards a draft whose save failed',async({page})=>{
 await mockWorkspace(page);let deleted=false,writes=0;const removed:string[]=[];
 await page.route('**/api/members/self/medication-plans**',route=>{
  const path=new URL(route.request().url()).pathname;
  if(route.request().method()==='PATCH'){writes++;return route.fulfill({status:503,json:{detail:{message:'计划保存失败'}}});}
  if(route.request().method()==='DELETE'){deleted=true;removed.push(path);return route.fulfill({json:{success:true}});}
  return route.fulfill({json:path.endsWith('/plan0')?plans[0]:{items:deleted?[]:[plans[0]],next_cursor:null}});
 });
 await page.goto('/health/self/medications/plans/plan0');
 await page.getByLabel('备注',{exact:true}).fill('尚未保存的计划草稿');await expect(page.getByRole('alert')).toContainText('计划保存失败');
 expect(writes).toBeGreaterThan(0);
 await page.locator('.report-timeline-item').click({button:'right'});await page.getByRole('menuitem',{name:'删除',exact:true}).click();
 await expect(page).toHaveURL(/\/plans$/);expect(removed).toEqual(['/api/members/self/medication-plans/plan0']);
 await expect(page.locator('.report-timeline-item')).toHaveCount(0);
});
