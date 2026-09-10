import {expect,test} from '@playwright/test';
import {mockWorkspace} from '../helpers/workspace';

for(const width of [1280,390])test(`nested additions use shared creation dialogs at ${width}px`,async({page},testInfo)=>{
 await mockWorkspace(page);await page.setViewportSize({width,height:900});let writes=0;
 await page.route('**/api/members/self/body-metrics/**',route=>{
  if(route.request().method()!=='GET')writes++;
  const path=new URL(route.request().url()).pathname;
  return route.fulfill({json:path.endsWith('/catalog')?{metrics:[{metric:'weight',label:'体重',unit:'kg',category:'body'}],meal_types:{breakfast:'早餐'},stages:{light:'浅睡',deep:'深睡'}}:path.endsWith('/records')?{items:[],total:0,next_offset:null}:{series:[],sources:[],total_records:0,coverage_from:null,coverage_to:null}});
 });
 await page.goto('/health/self/body-metrics/nutrition');await page.getByRole('button',{name:'＋ 创建记录',exact:true}).click();
 const parent=page.getByRole('dialog',{name:'创建记录',exact:true});
 const parentBox=(await parent.boundingBox())!;expect(parentBox.y).toBeGreaterThanOrEqual(0);expect(parentBox.y+parentBox.height).toBeLessThanOrEqual(900);
 await expect(parent.getByRole('button',{name:'完成',exact:true})).toBeInViewport();
 await expect(parent.getByRole('button',{name:'取消',exact:true})).toHaveCount(0);
 await parent.getByRole('button',{name:'＋ 添加食物',exact:true}).click();
 const food=page.getByRole('dialog',{name:'添加食物',exact:true});await expect(food).toBeVisible();
 const foodBox=(await food.boundingBox())!;expect(foodBox.width).toBe(parentBox.width);expect(foodBox.height).toBe(parentBox.height);
 await expect(food.locator('.dialog-titlebar').getByRole('button',{name:'返回上一级',exact:true})).toBeVisible();
 await expect(food.getByRole('button',{name:'取消',exact:true})).toHaveCount(0);
 await expect(parent).toHaveJSProperty('inert',true);await food.getByLabel('食物名称',{exact:true}).fill('取消的食物');await page.keyboard.press('Escape');
 await expect(food).toHaveCount(0);await expect(parent).toHaveJSProperty('inert',false);await expect(parent.getByText('食物 1',{exact:true})).toHaveCount(0);
 await parent.getByRole('button',{name:'＋ 添加食物',exact:true}).click();await food.getByLabel('食物名称',{exact:true}).fill('苹果');
 await food.screenshot({path:testInfo.outputPath(`food-${width}.png`)});const box=(await food.boundingBox())!;expect(box.x).toBeGreaterThanOrEqual(15);expect(box.x+box.width).toBeLessThanOrEqual(width-15);
 await food.getByRole('button',{name:'完成',exact:true}).click();await expect(food).toHaveCount(0);await expect(parent.getByText('食物 1',{exact:true})).toBeVisible();expect(writes).toBe(0);
 await parent.getByRole('button',{name:'关闭创建记录',exact:true}).click();
 await page.goto('/health/self/body-metrics/sleep');await page.getByRole('button',{name:'＋ 创建记录',exact:true}).click();await parent.getByRole('button',{name:'＋ 添加睡眠阶段',exact:true}).click();
 const stage=page.getByRole('dialog',{name:'添加睡眠阶段',exact:true});await expect(stage).toBeVisible();await stage.getByRole('button',{name:'返回上一级',exact:true}).click();
 await expect(parent.locator('.bm-stage-editor')).toHaveCount(0);await parent.getByRole('button',{name:'＋ 添加睡眠阶段',exact:true}).click();await stage.getByRole('button',{name:'完成',exact:true}).click();await expect(parent.locator('.bm-stage-editor')).toHaveCount(1);expect(writes).toBe(0);
});
