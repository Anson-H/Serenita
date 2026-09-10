import {test,expect} from '@playwright/test';
import {mockWorkspace} from '../helpers/workspace';
const drug={medication_id:'drug',generic_name:'目录药品',brand_name:null,strength:'5 mg',package_specification:'10 片/盒',prescription_type:'unknown',notes:'目录说明',leaflet_url:null,sources:[],created_at:'2026-09-01',updated_at:'2026-09-01'};
for(const width of [1280,390])test(`medication settings edit information and member inventory stays read only at ${width}`,async({page})=>{
 await mockWorkspace(page);await page.setViewportSize({width,height:900});
 let saved={...drug};let batches:any[]=[];const writes:string[]=[];
 await page.route('**/api/medication-catalog**',async route=>{
  const request=route.request();const path=new URL(request.url()).pathname;
  if(request.method()==='PATCH'){writes.push(path);saved={...saved,...request.postDataJSON()};return route.fulfill({json:saved});}
  return route.fulfill({json:path.endsWith('/drug')?saved:{items:[saved],total:1,next_cursor:null}});
 });
 await page.route('**/api/members/self/medications**',async route=>{
  const request=route.request();const url=new URL(request.url());
  if(request.method()==='POST'&&url.pathname.endsWith('/batches')){writes.push(url.pathname);const batch={...request.postDataJSON(),medication_batch_id:'batch',medication_id:'drug',member_id:'self'};batches=[batch];return route.fulfill({status:201,json:batch});}
  if(request.method()!=='GET')throw new Error('Unexpected member information write '+request.method()+' '+url.pathname);
  return route.fulfill({json:url.pathname.endsWith('/drug')?{...saved,member_id:'self',batches}:{items:url.searchParams.has('inventory_only')&&!batches.length?[]:[{...saved,member_id:'self'}],total:1,next_cursor:null}});
 });
 await page.goto('/setting');
 await page.getByRole('complementary',{name:'设置导航'}).getByRole('button',{name:'药品目录',exact:true}).click();
 await page.getByRole('button',{name:/目录药品.*5 mg/}).click();
 await page.getByRole('button',{name:'编辑浓度含量',exact:true}).click();
 await page.getByLabel('浓度含量',{exact:true}).fill('10 mg');
 await expect.poll(()=>saved.strength).toBe('10 mg');
 await expect(page.getByRole('button',{name:'补充原件',exact:true})).toBeVisible();
 await page.goto('/health/self/medications/catalog');
 await expect(page.getByRole('tab',{name:'药品库存',exact:true})).toBeVisible();
 await page.getByRole('button',{name:'添加药品批次',exact:true}).click();
 await page.getByRole('button',{name:'选择药品：未选择',exact:true}).click();
 await page.getByRole('dialog',{name:'切换药品',exact:true}).getByRole('button',{name:/目录药品/}).click();
 await expect(page.getByRole('dialog',{name:'切换药品',exact:true})).toHaveCount(0);
 const creation=page.getByRole('dialog',{name:'添加药品批次',exact:true});
 await expect(creation.getByRole('button',{name:'选择药品：目录药品',exact:true})).toBeVisible();
 await creation.getByLabel('数量',{exact:true}).fill('2.5');
 await expect(creation.getByLabel('数量',{exact:true})).toHaveValue('2.5');
 await creation.getByRole('button',{name:'完成',exact:true}).click();
 await expect(page).toHaveURL(/catalog\/drug$/);
 await expect(page.locator('.medication-editor')).toContainText('10 mg');
 await expect(page.getByRole('button',{name:'编辑浓度含量',exact:true})).toHaveCount(0);
 await expect(page.getByRole('button',{name:'补充原件',exact:true})).toHaveCount(0);
 await expect(page.getByRole('button',{name:'删除药品',exact:true})).toHaveCount(0);
 await expect(page.locator('.medication-editor input[type=file]')).toHaveCount(0);
 await expect(page.getByRole('heading',{name:'药品库存',exact:true})).toBeVisible();
 await expect(page.getByRole('region',{name:'用药详情',exact:true}).getByRole('button',{name:'添加药品批次',exact:true})).toBeVisible();
 expect(writes).toEqual(['/api/medication-catalog/drug','/api/members/self/medications/drug/batches']);
});

test('generic name remains required when a brand name exists',async({page})=>{
 await mockWorkspace(page);
 const saved={...drug,brand_name:'商品名'};
 const writes:unknown[]=[];
 await page.route('**/api/medication-catalog**',route=>{
  const request=route.request();
  if(request.method()==='PATCH'){writes.push(request.postDataJSON());return route.fulfill({json:{...saved,...request.postDataJSON()}});}
  return route.fulfill({json:new URL(request.url()).pathname.endsWith('/drug')?saved:{items:[saved],total:1,next_cursor:null}});
 });
 await page.goto('/setting');
 await page.getByRole('complementary',{name:'设置导航'}).getByRole('button',{name:'药品目录',exact:true}).click();
 await page.getByRole('button',{name:/商品名.*目录药品/}).click();
 await page.getByRole('button',{name:'编辑通用名',exact:true}).click();
 const input=page.getByLabel('通用名',{exact:true});
 await expect(input).toHaveAttribute('required','');
 await input.fill('');
 await input.blur();
 await expect(page.getByText('药品通用名不能为空。',{exact:true})).toBeVisible();
 expect(writes).toEqual([]);
});
