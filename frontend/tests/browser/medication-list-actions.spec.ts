import {expect,test,type Page,type Locator} from '@playwright/test';
import {mockWorkspace} from '../helpers/workspace';
import {expectSelectionReplacement} from '../helpers/selectionSpacing';

async function setup(page:Page,readonly=false){
  await mockWorkspace(page);
  if(readonly)await page.route('**/api/members',route=>route.fulfill({json:{access_revision:1,initial_member_id:'self',default_member_id:'self',members:[{member_id:'self',member_name:'本人',is_owned:false,can_edit:false,permission:'read'}]}}));
  let plan:any={medication_plan_id:'plan',member_id:'self',medication_id:'drug',medication_identity:{generic_name:'示例药品'},starts_at:'2026-09-01T00:00:00Z',start_precision:'date',timezone:'UTC',schedule:{kind:'daily',times:[{time:'08:00'},{time:'12:00'},{time:'20:00'}]}};
  const patches:any[]=[];const deletes:string[]=[];let fail=false;
  await page.route('**/api/members/self/medication-plans**',async route=>{
    if(route.request().method()==='PATCH'){
      patches.push(route.request().postDataJSON());
      if(fail)return route.fulfill({status:503,json:{detail:{message:'计划保存失败'}}});
      plan={...plan,...route.request().postDataJSON()};
    }
    return route.fulfill({json:new URL(route.request().url()).pathname.endsWith('/plan')?plan:{items:[plan],next_cursor:null}});
  });
  page.on('request',request=>{if(request.method()==='DELETE')deletes.push(request.url());});
  await page.goto('/health/self/medications/plans/plan');
  await expect(page.getByRole('button',{name:'用药时间',exact:true})).toBeVisible();
  return {patches,deletes,plan:()=>plan,setFail:(value:boolean)=>{fail=value;}};
}

async function openMenu(page:Page,row:Locator,touch:boolean){
  if(touch){
    await row.dispatchEvent('pointerdown',{pointerId:1,pointerType:'touch',isPrimary:true,button:0,clientX:150,clientY:400});
    await expect(page.getByRole('menu')).toBeVisible();
    await row.dispatchEvent('pointerup',{pointerId:1,pointerType:'touch',isPrimary:true,button:0});
    await row.dispatchEvent('click');
  }else await row.click({button:'right'});
  await expect(page.getByRole('menuitem',{name:'多选',exact:true})).toBeVisible();
}

for(const width of [1280,390])for(const section of ['plans'] as ('catalog'|'plans')[])test(`${section} list menu, paginated count and failed deletion at ${width}px`,async({page},testInfo)=>{
  await mockWorkspace(page);await page.setViewportSize({width,height:900});
  const resource=section==='catalog'?'medications':'medication-plans';
  const key=section==='catalog'?'medication_id':'medication_plan_id';
  const label=section==='catalog'?'药品':'用药计划';const unit=section==='catalog'?'种':'条';
  const creation=section==='catalog'?'添加药品':'创建用药计划';
  let records=[1,2].map(n=>({[key]:`item${n}`,member_id:'self',generic_name:`测试药品${n}`,medication_identity:{generic_name:`测试药品${n}`},starts_at:null}));
  const deleted:string[]=[];let fail=true;let failAll=true;
  await page.route(`**/api/members/self/${resource}**`,route=>{
    const url=new URL(route.request().url());const id=url.pathname.split('/').at(-1)!;
    if(route.request().method()==='DELETE'){
      deleted.push(id);
      if(failAll||fail&&id==='item2')return route.fulfill({status:503,json:{detail:{message:'测试删除暂时失败'}}});
      records=records.filter(row=>row[key]!==id);return route.fulfill({json:{deleted:true}});
    }
    if(id.startsWith('item'))return route.fulfill({json:records.find(row=>row[key]===id)});
    const matching=url.searchParams.get('query')?records.filter(row=>row.generic_name.includes(url.searchParams.get('query')!)):records;
    const next=url.searchParams.has('cursor');
    return route.fulfill({json:{items:next?matching.slice(1):matching.slice(0,1),total:matching.length,next_cursor:!next&&matching.length>1?'next':null}});
  });
  await page.goto(`/health/self/medications/${section}`);
  const list=page.getByRole('region',{name:'用药记录列表',exact:true});
  const count=list.locator('.object-list-count');const rows=list.locator('.report-timeline-item');
  await expect(count).toHaveText(`共 2 ${unit}${label}`);await expect(rows).toHaveCount(1);
  await list.getByRole('button',{name:'加载更多',exact:true}).click();
  await expect(rows).toHaveCount(2);await expect(count).toHaveText(`共 2 ${unit}${label}`);
  const lastBox=(await rows.last().boundingBox())!,countBox=(await count.boundingBox())!;
  expect(countBox.y-lastBox.y-lastBox.height).toBeCloseTo(15,0);
  const firstRowY=(await rows.first().boundingBox())!.y;
  await openMenu(page,rows.first(),width===390);
  await page.getByRole('menuitem',{name:'多选',exact:true}).click();
  await expect(list.getByRole('status')).toHaveText(`已选择 1 ${unit}${label}`);
  await expect(list.getByRole('button',{name:creation,exact:true})).toHaveCount(0);
  const heading=list.locator('.list-selection-heading');
  await expectSelectionReplacement(heading,list.locator(section==='catalog'?'.medication-search':'.medication-plan-filters'));
  expect((await rows.first().boundingBox())!.y).toBeCloseTo(firstRowY,0);
  for(const button of await heading.getByRole('button').all()){
    await expect(button).toHaveText('');await expect(button).toHaveCSS('width','40px');
  }
  await list.getByRole('button',{name:`全选${label}`,exact:true}).click();
  await expect(list.getByRole('checkbox')).toHaveCount(2);
  const remove=list.getByRole('button',{name:'删除',exact:true});
  await expect(remove).toHaveClass(/control--compact/);
  await list.screenshot({path:testInfo.outputPath(`${section}-selection-${width}.png`)});
  const refreshed=page.waitForResponse(response=>response.url().includes(`${resource}?`)&&!new URL(response.url()).searchParams.has('cursor'));
  await remove.click();
  await refreshed;
  await expect(list.getByRole('checkbox')).toHaveCount(2);
  await expect(list.getByRole('status')).toHaveText(`已选择 2 ${unit}${label}`);
  await expect(count).toHaveText(`共 2 ${unit}${label}`);
  failAll=false;deleted.length=0;await remove.click();
  await expect(list.getByRole('alert')).toContainText('测试删除暂时失败');
  await expect(list.getByRole('checkbox')).toHaveCount(1);
  await expect(list.getByRole('checkbox')).toBeChecked();await expect(count).toHaveText(`共 1 ${unit}${label}`);
  expect(deleted).toEqual(['item1','item2']);fail=false;await remove.click();
  await expect(rows).toHaveCount(0);await expect(count).toHaveCount(0);
  await expect(list.getByRole('button',{name:creation,exact:true})).toBeVisible();
  expect(deleted).toEqual(['item1','item2','item2']);
});

for(const section of ['catalog','plans'] as const)test(`${section} read-only list retains count without a context menu`,async({page})=>{
  await mockWorkspace(page);
  await page.route('**/api/members',route=>route.fulfill({json:{access_revision:1,initial_member_id:'self',default_member_id:'self',members:[{member_id:'self',member_name:'本人',is_owned:false,can_edit:false,permission:'read'}]}}));
  const resource=section==='catalog'?'medications':'medication-plans';
  await page.route(`**/api/members/self/${resource}**`,route=>route.fulfill({json:{items:[{medication_id:'drug',medication_plan_id:'plan',generic_name:'只读药品',medication_identity:{generic_name:'只读药品'},starts_at:null}],total:1,next_cursor:null}}));
  await page.goto(`/health/self/medications/${section}`);
  const list=page.getByRole('region',{name:'用药记录列表',exact:true});
  await expect(list.locator('.object-list-count')).toHaveText(section==='catalog'?'共 1 种药品':'共 1 条用药计划');
  await list.locator('.report-timeline-item').click({button:'right'});
  await expect(page.getByRole('menu')).toHaveCount(0);
});

for(const section of ['plans'] as ('catalog'|'plans')[])test(`${section} current item deletion waits for saving and list selection keeps detail deletion visible`,async({page})=>{
  await mockWorkspace(page);
  const resource=section==='catalog'?'medications':'medication-plans';
  const fullDelete=section==='catalog'?'删除药品':'删除用药计划';
  const item={member_id:'self',medication_id:'drug',...(section==='plans'?{medication_plan_id:'item'}:{medication_id:'item'}),generic_name:'待删除药品',medication_identity:{generic_name:'待删除药品'},notes:null,starts_at:'2026-09-01T00:00:00Z',start_precision:'date',timezone:'UTC',schedule:null};
  let release!:()=>void;const pending=new Promise<void>(resolve=>{release=resolve;});
  const calls:string[]=[];let removed=false;
  await page.route(`**/api/members/self/${resource}**`,async route=>{
    const request=route.request();
    if(request.method()==='PATCH'){calls.push('save-start');await pending;calls.push('save-end');return route.fulfill({json:{...item,...request.postDataJSON()}});}
    if(request.method()==='DELETE'){calls.push('delete');removed=true;return route.fulfill({json:{deleted:true}});}
    return route.fulfill({json:new URL(request.url()).pathname.endsWith('/item')?item:{items:removed?[]:[item],total:removed?0:1,next_cursor:null}});
  });
  await page.goto(`/health/self/medications/${section}/item`);
  const list=page.getByRole('region',{name:'用药记录列表',exact:true});const row=list.locator('.report-timeline-item');
  await row.focus();await row.press('Shift+F10');await page.getByRole('menuitem',{name:'多选',exact:true}).click();
  await expect(page.getByRole('button',{name:fullDelete,exact:true})).toBeVisible();
  await page.keyboard.press('Escape');await expect(page.getByRole('button',{name:fullDelete,exact:true})).toBeVisible();
  await page.getByLabel('备注',{exact:true}).fill('正在保存');await expect.poll(()=>calls).toEqual(['save-start']);
  await row.click({button:'right'});await page.getByRole('menuitem',{name:'删除',exact:true}).click();
  expect(calls).toEqual(['save-start']);release();
  await expect(page).toHaveURL(new RegExp(`/medications/${section}$`));
  await expect(row).toHaveCount(0);await expect(list.locator('.object-list-count')).toHaveCount(0);
  expect(calls).toEqual(['save-start','save-end','delete']);
});

for(const width of [1280,390])test(`time context actions select by time and Escape keeps settings at ${width}px`,async({page},testInfo)=>{
  await page.setViewportSize({width,height:900});const state=await setup(page);
  await page.getByRole('button',{name:'用药时间',exact:true}).click();
  const screen=page.locator('.medication-schedule-page');
  await expect(screen.getByRole('button',{name:/删除时间/})).toHaveCount(0);
  const first=screen.getByRole('button',{name:'时间 1',exact:true});
  await openMenu(page,first,width===390);
  await page.getByRole('menuitem',{name:'多选',exact:true}).click();
  await expect(screen.getByRole('checkbox').first()).toBeChecked();
  await screen.getByRole('checkbox').first().focus();await page.keyboard.press('Escape');
  await expect(screen).toBeVisible();await expect(screen.getByRole('checkbox')).toHaveCount(0);
  await first.focus();await first.press('Shift+F10');await page.getByRole('menuitem',{name:'多选',exact:true}).click();
  await screen.getByRole('button',{name:'全选用药时间',exact:true}).click();
  await expect(screen.getByRole('status')).toContainText('已选择 3 个时间');
  await screen.getByRole('checkbox').nth(1).click();
  await screen.screenshot({path:testInfo.outputPath(`time-multiselect-${width}.png`)});
  await screen.getByRole('button',{name:'删除',exact:true}).click();
  await expect.poll(()=>state.plan().schedule.times).toEqual([{time:'12:00'}]);
  await expect(first).toHaveText(/\d{2}:\d{2}/);
  await first.click({button:'right'});await page.getByRole('menuitem',{name:'删除',exact:true}).click();
  await expect.poll(()=>state.plan().schedule.times).toEqual([]);
  await expect(screen.getByLabel('每日次数',{exact:true})).toBeVisible();
});

test('readonly plan times expose no removal menu',async({page})=>{
  await setup(page,true);
  await page.getByRole('button',{name:'用药时间',exact:true}).click();
  await page.locator('.medication-schedule-page .field-row').first().click({button:'right'});
  await expect(page.getByRole('menu')).toHaveCount(0);
  await expect(page.getByRole('button',{name:'添加用药时间',exact:true})).toHaveCount(0);
});
