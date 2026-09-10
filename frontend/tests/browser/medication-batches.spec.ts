import {expect,test} from '@playwright/test';
import {mockWorkspace} from '../helpers/workspace';
const batch={medication_batch_id:'batch1',medication_id:'drug1',quantity:'2',expires_on:'2027-03-15',notes:null};
const drug={medication_id:'drug1',member_id:'self',generic_name:'批次验收药品',prescription_type:'unknown',sources:[],batches:[batch]};

test.describe('batch expiration visibility',()=>{
 test.use({timezoneId:'Asia/Shanghai'});
 test('expired batches remain visible and clearing expiry updates detail and list',async({page})=>{
  await mockWorkspace(page);await page.setViewportSize({width:390,height:900});
  await page.clock.setFixedTime(new Date('2026-09-07T16:30:00Z'));
  let current={...drug,batches:[
   {...batch,expires_on:'2026-09-07',quantity:'0'},
   {...batch,medication_batch_id:'today',expires_on:'2026-09-08'},
   {...batch,medication_batch_id:'future',expires_on:'2026-09-09'},
   {...batch,medication_batch_id:'unknown',expires_on:null}
  ]};
  await page.route('**/api/members/self/medications**',route=>{
   const url=new URL(route.request().url());
   if(route.request().method()==='PATCH'){
    const saved={...current.batches[0],...route.request().postDataJSON()};current.batches[0]=saved;
    return route.fulfill({json:saved});
   }
   return route.fulfill({json:url.pathname.endsWith('/drug1')?current:{items:[current],next_cursor:null}});
  });
  await page.goto('/health/self/medications/catalog/drug1');
  const expired=page.locator('[data-medication-batch="batch1"]');
  await expect(expired).toContainText('已过期');await expect(expired).toContainText('2026年9月7日');
  for(const id of ['today','future','unknown'])await expect(page.locator(`[data-medication-batch="${id}"]`)).not.toContainText('已过期');
  await expired.click();const detail=page.locator('.medication-detail');
  await expect(detail.getByText('已过期',{exact:true})).toBeVisible();
  await expect(detail.locator('.field-label')).toHaveText(['有效期','数量','备注']);
  await page.getByRole('button',{name:'有效期',exact:true}).click();
  await page.getByRole('dialog',{name:'有效期选择器'}).getByRole('button',{name:'未知',exact:true}).click();
  await expect(detail.getByText('已过期',{exact:true})).toHaveCount(0);
  await expect.poll(()=>current.batches[0].expires_on).toBeNull();
  await detail.getByRole('button',{name:'返回上一级',exact:true}).click();
  await expect(expired).toBeVisible();await expect(expired).not.toContainText('已过期');
  await expect(expired).toContainText('未记录');
 });

 test('read-only expiry changes at local midnight without reloading',async({page})=>{
  await mockWorkspace(page);await page.clock.install({time:new Date('2026-09-08T15:58:00Z')});
  await page.route('**/api/members',route=>route.fulfill({json:{access_revision:1,default_member_id:'self',initial_member_id:'self',last_member_id:'self',startup_mode:'last_used',members:[{member_id:'self',member_name:'共享成员',account_id:'owner',owner_account:'owner',is_owned:false,can_edit:false,permission:'read'}]}}));
  const current={...drug,batches:[{...batch,expires_on:'2026-09-08'}]};
  await page.route('**/api/members/self/medications**',route=>route.fulfill({json:new URL(route.request().url()).pathname.endsWith('/drug1')?current:{items:[current],next_cursor:null}}));
  await page.goto('/health/self/medications/catalog/drug1/batches/batch1');
  const detail=page.locator('.medication-detail');
  await expect(detail.getByText('2026年9月8日',{exact:true})).toBeVisible();
  await expect(detail.getByText('已过期',{exact:true})).toHaveCount(0);
  await page.clock.fastForward(121000);
  await expect(detail.getByText('已过期',{exact:true})).toBeVisible();
  await expect(page.getByRole('textbox')).toHaveCount(0);
  await detail.getByRole('button',{name:'返回上一级',exact:true}).click();
  await expect(page.locator('[data-medication-batch="batch1"]')).toContainText('已过期');
 });
});

for(const width of [1280,390])test(`batch autosave preserves failed drafts and creates once at ${width}px`,async({page})=>{
 await mockWorkspace(page);await page.setViewportSize({width,height:900});let current={...drug,batches:[{...batch}]};let fail=true;let creates=0;let patches=0;
 await page.route('**/api/members/self/medications**',route=>{
  const method=route.request().method(),url=new URL(route.request().url());
  if(method==='PATCH'){patches++;if(fail)return route.fulfill({status:503,json:{detail:{message:'批次保存失败'}}});const id=url.pathname.split('/').pop();const saved={...current.batches.find(b=>b.medication_batch_id===id)!,...route.request().postDataJSON()};current={...current,batches:current.batches.map(b=>b.medication_batch_id===id?saved:b)};return route.fulfill({json:saved});}
  if(method==='POST'){creates++;const saved={...batch,...route.request().postDataJSON(),medication_batch_id:'batch2'};current.batches.push(saved);return route.fulfill({json:saved});}
  return route.fulfill({json:url.pathname.endsWith('/drug1')?current:{items:[current],next_cursor:null}});
 });
 await page.goto('/health/self/medications/catalog/drug1');const detail=page.locator('.medication-detail');
 await page.locator('[data-medication-batch="batch1"]').click();
 await expect(detail.locator('.workspace-navigation-toolbar')).toHaveCount(1);
 await expect(detail.locator('.field-label')).toHaveText(['有效期','数量','备注']);
 await expect(page.getByLabel('数量单位',{exact:true})).toHaveCount(0);
 await expect(page.getByRole('button',{name:/^(保存批次|取消)$/})).toHaveCount(0);
 await page.getByLabel('数量',{exact:true}).fill('3');await expect(page.getByRole('alert')).toContainText('批次保存失败');
 await expect(page.getByLabel('数量',{exact:true})).toHaveValue('3');
 await detail.getByRole('button',{name:'返回上一级',exact:true}).click();await expect(page).toHaveURL(/batches\/batch1$/);
 fail=false;await page.getByLabel('数量',{exact:true}).fill('4');await expect.poll(()=>current.batches[0].quantity).toBe('4');
 await expect(page).toHaveURL(/batches\/batch1$/);await expect(page.getByRole('alert')).toHaveCount(0);
 await detail.getByRole('button',{name:'返回上一级',exact:true}).click();await expect(page.locator('[data-medication-batch="batch1"]')).toContainText('4');
 await page.getByRole('button',{name:'添加药品批次',exact:true}).click();
 const dialog=page.getByRole('dialog',{name:'添加药品批次',exact:true});await expect(dialog).toHaveAttribute('aria-modal','true');
 await dialog.getByLabel('数量',{exact:true}).fill('1.250');await expect(page).toHaveURL(/catalog\/drug1$/);expect(creates).toBe(0);
 await dialog.getByRole('button',{name:'关闭添加药品批次',exact:true}).click();await expect(dialog).toHaveCount(0);expect(creates).toBe(0);
 await page.getByRole('button',{name:'添加药品批次',exact:true}).click();await dialog.getByLabel('数量',{exact:true}).fill('1.250');
 await dialog.getByLabel('备注',{exact:true}).fill('新批次');await dialog.getByRole('button',{name:'完成',exact:true}).click();
 await expect(dialog).toHaveCount(0);await expect.poll(()=>creates).toBe(1);await expect(page.locator('[data-medication-batch="batch2"]')).toBeVisible();
 await page.locator('[data-medication-batch="batch2"]').click();await expect(page.getByLabel('备注',{exact:true})).toHaveValue('新批次');
 await page.getByLabel('备注',{exact:true}).fill('批次更新');await expect.poll(()=>current.batches[1].notes).toBe('批次更新');expect(creates).toBe(1);expect(patches).toBeGreaterThan(1);

});

for(const width of [1280,390])test(`batch context selection retains failed deletions at ${width}px`,async({page},testInfo)=>{
 await mockWorkspace(page);await page.setViewportSize({width,height:900});let current={...drug,batches:[batch,{...batch,medication_batch_id:'batch2',quantity:'3'}]};let fail=true;const deleted:string[]=[];
 await page.route('**/api/members/self/medications**',route=>{
  const url=new URL(route.request().url());if(route.request().method()==='DELETE'){const id=url.pathname.split('/').pop()!;if(id==='batch2'&&fail)return route.fulfill({status:503,json:{detail:{message:'删除失败'}}});deleted.push(id);current.batches=current.batches.filter(b=>b.medication_batch_id!==id);return route.fulfill({json:{deleted:true}});}
  return route.fulfill({json:url.pathname.endsWith('/drug1')?current:{items:[current],next_cursor:null}});
 });
 await page.goto('/health/self/medications/catalog/drug1');
 const row=page.locator('[data-medication-batch="batch1"]');
 const originalRowY=(await row.boundingBox())!.y;
 await row.hover();
 const corners=await row.evaluate(element=>{const style=getComputedStyle(element);return [style.borderTopLeftRadius,style.borderTopRightRadius,style.borderBottomLeftRadius,style.borderBottomRightRadius];});
 expect(corners.every(value=>parseFloat(value)>0)).toBe(true);
 await row.click({button:'right'});await expect(page.getByRole('menu')).toBeVisible();
 await page.getByRole('menuitem',{name:'多选',exact:true}).click();await expect(page.getByRole('checkbox')).toHaveCount(2);
 const bar=page.locator('.list-selection-heading');
 const bottom=page.getByRole('group',{name:'药品批次批量操作',exact:true});
 await expect(bar.getByRole('button',{name:'删除',exact:true})).toHaveCount(0);
 await expect(bottom.getByRole('button',{name:'删除',exact:true})).toHaveClass(/control--compact/);
 await expect(bottom.getByRole('button',{name:'删除',exact:true})).toHaveCSS('font-size','13px');
 await expect(page.getByRole('button',{name:'删除药品',exact:true})).toHaveCount(0);
 await expect(bar.getByRole('button',{name:'全选药品批次',exact:true})).toHaveText('');
 await expect(bar.getByRole('button',{name:'退出药品批次多选',exact:true})).toHaveText('');
 await expect(bar.getByRole('status')).toHaveCSS('font-size','15px');
 for(const button of await bar.getByRole('button').all()){await expect(button).toHaveCSS('width','40px');await expect(button).toHaveCSS('height','40px');await expect(button).not.toHaveClass(/control--compact/);}
 const barBox=(await bar.boundingBox())!,rowBox=(await row.boundingBox())!;
 expect(rowBox.y-(barBox.y+barBox.height)).toBeCloseTo(0,0);
 expect(rowBox.y).toBeCloseTo(originalRowY,0);
 const lastRowBox=(await page.locator('[data-medication-batch="batch2"]').boundingBox())!,bottomBox=(await bottom.boundingBox())!;
 expect(bottomBox.y-(lastRowBox.y+lastRowBox.height)).toBeGreaterThanOrEqual(15);
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
 await page.locator('.medication-editor').screenshot({path:testInfo.outputPath(`compact-batch-selection-${width}.png`)});
 await page.getByRole('button',{name:'全选药品批次',exact:true}).click();
 await expect(page.getByRole('button',{name:'取消全选药品批次',exact:true})).toHaveText('');
 await expect(page.getByRole('button',{name:'取消全选药品批次',exact:true})).toHaveAttribute('aria-pressed','true');
 await expect(page.getByRole('status')).toContainText('已选择 2 个批次');await page.getByRole('button',{name:'删除',exact:true}).click();
 await expect(page.getByRole('alert')).toContainText('1 个批次未删除');await expect(page.getByRole('checkbox')).toHaveCount(1);await expect(page.getByRole('checkbox')).toBeChecked();expect(deleted).toEqual(['batch1']);
 fail=false;await page.getByRole('button',{name:'删除',exact:true}).click();await expect(page.locator('[data-medication-batch="batch2"]')).toHaveCount(0);await expect(page.getByRole('button',{name:'添加药品批次',exact:true})).toBeVisible();
 await expect(page.getByRole('button',{name:'删除药品',exact:true})).toHaveCount(0);
});

test('read-only batch details have no writes or context actions',async({page})=>{
 await mockWorkspace(page);
 await page.route('**/api/members',route=>route.fulfill({json:{access_revision:1,default_member_id:'self',initial_member_id:'self',last_member_id:'self',startup_mode:'last_used',members:[{member_id:'self',member_name:'共享成员',account_id:'owner',owner_account:'owner',is_owned:false,can_edit:false,permission:'read'}]}}));
 await page.route('**/api/members/self/medications**',route=>route.fulfill({json:new URL(route.request().url()).pathname.endsWith('/drug1')?drug:{items:[drug],next_cursor:null}}));
 await page.goto('/health/self/medications/catalog/drug1/batches/batch1');await expect(page.getByText('2027年3月15日',{exact:true})).toBeVisible();
 await expect(page.getByRole('button',{name:'删除批次',exact:true})).toHaveCount(0);await expect(page.getByRole('textbox')).toHaveCount(0);
 await page.locator('.medication-detail').getByRole('button',{name:'返回上一级',exact:true}).click();await page.locator('[data-medication-batch="batch1"]').click({button:'right'});await expect(page.getByRole('menu')).toHaveCount(0);
});

test('an uncertain batch creation retries the same command then saves later edits',async({page})=>{
 await mockWorkspace(page);let current={...drug,batches:[] as typeof batch[]};const posts:{body:unknown;key:string|undefined}[]=[];
 let release!:()=>void;const gate=new Promise<void>(resolve=>{release=resolve;});
 await page.route('**/api/members/self/medications**',async route=>{
  const url=new URL(route.request().url()),method=route.request().method();
  if(method==='POST'){
   const body=route.request().postDataJSON();posts.push({body,key:route.request().headers()['idempotency-key']});
   if(posts.length===1){await gate;return route.fulfill({status:503,json:{detail:{message:'连接中断'}}});}
   const saved={...batch,...body};current.batches=[saved];return route.fulfill({json:saved});
  }
  if(method==='PATCH'){current.batches[0]={...current.batches[0],...route.request().postDataJSON()};return route.fulfill({json:current.batches[0]});}
  return route.fulfill({json:url.pathname.endsWith('/drug1')?current:{items:[current],next_cursor:null}});
 });
 await page.goto('/health/self/medications/catalog/drug1');await page.getByRole('button',{name:'添加药品批次',exact:true}).click();await page.getByLabel('数量',{exact:true}).fill('1');await page.getByRole('button',{name:'完成',exact:true}).click();await expect.poll(()=>posts.length).toBe(1);
 await expect(page.getByLabel('数量',{exact:true})).toBeDisabled();release();await expect(page.getByRole('alert')).toContainText('连接中断');
 await page.getByLabel('数量',{exact:true}).fill('3');await page.getByRole('button',{name:'完成',exact:true}).click();await expect(page.getByRole('dialog',{name:'添加药品批次',exact:true})).toHaveCount(0);await page.locator('[data-medication-batch="batch1"]').click();await expect(page.getByLabel('数量',{exact:true})).toHaveValue('3');
 expect(posts).toHaveLength(2);expect(posts[0]).toEqual(posts[1]);expect(current.batches).toHaveLength(1);expect(current.batches[0].quantity).toBe('3');
 await page.reload();await expect(page.getByLabel('数量',{exact:true})).toHaveValue('3');
});

test('batch creation waits for confirmation and keeps its parent dialog after cancelling a picker', async ({page}) => {
 await mockWorkspace(page);let posts=0;
 await page.route('**/api/members/self/medications**',route=>{if(route.request().method()==='POST')posts++;return route.fulfill({json:new URL(route.request().url()).pathname.endsWith('/drug1')?drug:{items:[drug],next_cursor:null}});});
 await page.goto('/health/self/medications/catalog/drug1');await page.getByRole('button',{name:'添加药品批次',exact:true}).click();
 const dialog=page.getByRole('dialog',{name:'添加药品批次',exact:true});
 await dialog.getByLabel('数量',{exact:true}).fill('1');await dialog.getByRole('button',{name:'有效期',exact:true}).click();
 const picker=page.getByRole('dialog',{name:'有效期选择器',exact:true});await picker.getByRole('textbox',{name:'年份',exact:true}).fill('');
 await page.keyboard.press('Escape');await expect(picker).toHaveCount(0);await expect(dialog).toBeVisible();await expect(dialog.getByLabel('数量',{exact:true})).toHaveValue('1');
 await page.keyboard.press('Escape');await expect(dialog).toHaveCount(0);expect(posts).toBe(0);await expect(page.getByRole('button',{name:'添加药品批次',exact:true})).toBeFocused();
});
