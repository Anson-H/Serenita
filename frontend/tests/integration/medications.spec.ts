import {expect,test} from '@playwright/test';

test('unified notification setting persists through the real account API',async({page})=>{
  await page.goto('/');
  await page.locator('input[name="account"]').fill('integration');
  await page.locator('input[name="password"]').fill('test-password');
  await page.locator('form').getByRole('button',{name:'登录',exact:true}).click();
  await expect(page.locator('.conversation-composer textarea')).toBeVisible();
  const path='/api/account-settings/notifications';
  const initial=await(await page.request.get(path)).json();
  try{
    await page.goto('/setting');await page.getByRole('complementary',{name:'设置导航'}).getByRole('button',{name:'通知',exact:true}).click();
    const toggle=page.getByRole('switch',{name:'总通知',exact:true});
    await expect(toggle).toBeEnabled();
    await toggle.click();
    await expect.poll(async()=> (await(await page.request.get(path)).json()).notifications_enabled).toBe(!initial.notifications_enabled);
    await page.reload();await page.getByRole('complementary',{name:'设置导航'}).getByRole('button',{name:'通知',exact:true}).click();
    await expect(page.getByRole('switch',{name:'总通知',exact:true})).toBeChecked({checked:!initial.notifications_enabled});
    expect((await page.request.get('/api/notifications')).status()).toBe(200);
  }finally{await page.request.put(path,{data:{medication_due_enabled:initial.medication_due_enabled,medication_expired_enabled:initial.medication_expired_enabled,answer_completed_enabled:initial.answer_completed_enabled}});}
});

for(const width of [1280,390]) test(`account medication settings, member stock and plans use distinct write APIs at ${width}px`,async({page})=>{
  test.setTimeout(60000);
  await page.setViewportSize({width,height:900});
  await page.goto('/');await page.locator('input[name="account"]').fill('integration');await page.locator('input[name="password"]').fill('test-password');
  await page.locator('form').getByRole('button',{name:'登录',exact:true}).click();await expect(page.locator('.conversation-composer textarea')).toBeVisible();
  const auth=await(await page.request.get('/api/auth/session')).json();const headers={'X-Serenita-Account-ID':auth.account_id};
  const member=(await(await page.request.post('/api/members',{headers,data:{member_name:`库存验收 ${width}`}})).json()).member_id;
  const base=`/api/members/${member}`,name=`设置药品 ${width}`;let medicationId='';
  try{
    await page.goto('/setting');await page.getByRole('complementary',{name:'设置导航'}).getByRole('button',{name:'药品目录',exact:true}).click();
    await page.getByRole('button',{name:'添加药品',exact:true}).click();
    const dialog=page.getByRole('dialog',{name:'添加药品',exact:true});
    await dialog.getByLabel('商品名',{exact:true}).fill(name);await dialog.getByLabel('包装规格',{exact:true}).fill('10 片/盒');
    await dialog.getByRole('button',{name:'完成',exact:true}).click();await expect(dialog).toHaveCount(0);
    const directory=await(await page.request.get('/api/medication-catalog?query='+encodeURIComponent(name))).json();
    expect(directory.items).toHaveLength(1);medicationId=directory.items[0].medication_id;
    const catalogPath=`/api/medication-catalog/${medicationId}`;
    expect(directory.items[0]).not.toHaveProperty('member_id');
    await page.getByRole('button',{name:'编辑通用名',exact:true}).click();await page.getByLabel('通用名',{exact:true}).fill('目录通用名');
    await expect.poll(async()=>(await(await page.request.get(catalogPath)).json()).generic_name).toBe('目录通用名');
    await page.locator('.medication-editor input[type=file]').setInputFiles({name:'说明书.txt',mimeType:'text/plain',buffer:Buffer.from('已保存的药品说明文字')});
    await expect(page.getByRole('button',{name:'打开原件预览，共 1 个关联文件',exact:true})).toBeVisible();
    await page.goto(`/health/${member}/medications/catalog`);await expect(page.getByRole('tab',{name:'药品库存',exact:true})).toBeVisible();
    await expect(page.locator('.report-timeline-item')).toHaveCount(0);
    await page.getByRole('button',{name:'添加药品批次',exact:true}).click();await page.getByRole('button',{name:'选择药品：未选择',exact:true}).click();
    await page.getByRole('dialog',{name:'切换药品',exact:true}).getByRole('button',{name:new RegExp(name)}).click();
    const inventory=page.getByRole('dialog',{name:'添加药品批次',exact:true});await inventory.getByLabel('数量',{exact:true}).fill('1.250');await expect(inventory.getByLabel('数量',{exact:true})).toHaveValue('1.250');
    await inventory.getByRole('button',{name:'完成',exact:true}).click();await expect(page).toHaveURL(new RegExp(`/catalog/${medicationId}$`));
    await expect(page.getByRole('button',{name:'编辑通用名',exact:true})).toHaveCount(0);await expect(page.getByRole('button',{name:'补充原件',exact:true})).toHaveCount(0);
    await page.getByRole('button',{name:'打开原件预览，共 1 个关联文件',exact:true}).click();await expect(page.getByRole('dialog').locator('pre')).toHaveText('已保存的药品说明文字');await page.keyboard.press('Escape');
    const stock=await(await page.request.get(`${base}/medications/${medicationId}`)).json();expect(stock.batches[0].quantity).toBe('1.25');
    expect((await page.request.patch(`${base}/medications/${medicationId}`,{headers,data:{generic_name:'禁止写入'}})).status()).toBe(405);
    expect((await page.request.post(`${base}/medications/${medicationId}/source-files`,{headers,multipart:{files:{name:'blocked.txt',mimeType:'text/plain',buffer:Buffer.from('禁止写入')}}})).status()).toBe(404);
    // A plan references the same catalog entry and does not copy its name or files.
    const planResponse=await page.request.post(`${base}/medication-plans`,{headers:{...headers,'Idempotency-Key':crypto.randomUUID()},data:{medication_id:medicationId,starts_at:'2026-09-01T00:00:00+08:00',start_precision:'date',timezone:'Asia/Shanghai',dose_text:'按已确认安排'}});
    expect(planResponse.status()).toBe(201);const plan=await planResponse.json();
    await page.goto(`/health/${member}/medications/plans/${plan.medication_plan_id}`);await expect(page.getByRole('region',{name:'计划药品',exact:true})).toContainText('目录通用名');
    await page.request.patch(catalogPath,{headers,data:{generic_name:'已修正名称'}});await page.reload();await expect(page.getByRole('region',{name:'计划药品',exact:true})).toContainText('已修正名称');
    expect((await page.request.delete(catalogPath,{headers})).status()).toBe(409);
    expect((await page.request.get(`${base}/medication-plans/${plan.medication_plan_id}`)).status()).toBe(200);
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
    await page.request.delete(base,{headers});expect((await page.request.get(catalogPath)).status()).toBe(200);
    expect((await page.request.delete(catalogPath,{headers})).status()).toBe(200);medicationId='';
  }finally{await page.request.delete(base,{headers});if(medicationId)await page.request.delete(`/api/medication-catalog/${medicationId}`,{headers});}
});
