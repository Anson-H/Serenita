import {expect,test,type Page} from '@playwright/test';
import {writeFile} from 'node:fs/promises';

test('210 actual renders: ten accounts, 100 plans each, due wakeup and answer completion without recovery',async({browser,page},testInfo)=>{
 test.setTimeout(180000);
 const base='http://127.0.0.1:4176';
 const fixture='http://127.0.0.1:8186/integration/notifications';
 const seed=await page.request.post(`${fixture}/seed`);expect(seed.ok(),await seed.text()).toBe(true);
 const setup=await seed.json();
 const contexts=[];const pages:Page[]=[];
 try{
  for(let n=0;n<10;n++){
   const context=await browser.newContext({baseURL:base});contexts.push(context);
   await context.addInitScript(()=>{
    const state={signal:0,connectionErrors:0,connectionOpens:0,renders:[] as {id:string;rendered_at:number;signal_at:number}[]};
    Object.assign(window,{notificationAcceptance:state});
    const Native=window.EventSource;
    window.EventSource=class extends Native{constructor(url:string|URL,config?:EventSourceInit){super(url,config);this.addEventListener('notifications_changed',()=>{state.signal=Date.now();});this.addEventListener('error',()=>{state.connectionErrors++;});this.addEventListener('open',()=>{state.connectionOpens++;});}};
    const seen=new Set<string>();
    new MutationObserver(()=>{
     for(const element of document.querySelectorAll<HTMLElement>('[data-notification-id]')){
      const id=element.dataset.notificationId!;if(seen.has(id))continue;seen.add(id);
      const signal=state.signal;
      requestAnimationFrame(()=>requestAnimationFrame(()=>{if(element.isConnected)state.renders.push({id,rendered_at:Date.now(),signal_at:signal});else seen.delete(id);}));
     }
    }).observe(document,{childList:true,subtree:true});
   });
   const login=await context.request.post(`${base}/api/auth/sign_in`,{data:{account:n===0?'integration':`notification${n}`,password:'test-password'}});
   expect(login.ok(),await login.text()).toBe(true);
   const target=await context.newPage();pages.push(target);await target.goto('/notifications');
   await expect(target.getByRole('region',{name:'通知中心'})).toBeVisible();
  }
  const arm=await page.request.post(`${fixture}/arm`);expect(arm.ok(),await arm.text()).toBe(true);
  const deadline=await arm.json();
  for(let n=0;n<16;n++){
   const saved=await page.request.post(`${fixture}/answer`);expect(saved.ok(),await saved.text()).toBe(true);
   await Promise.all(pages.map(p=>expect(p.locator('.notification-card').filter({hasText:'回答已生成'})).toHaveCount(n+1,{timeout:5000})));
  }
  await Promise.all(pages.map(p=>expect(p.locator('.notification-card').filter({hasText:'用药时间到了'})).toHaveCount(5,{timeout:70000})));
  await Promise.all(pages.map(p=>expect.poll(()=>p.evaluate(()=>((window as unknown as {notificationAcceptance:{renders:unknown[]}}).notificationAcceptance.renders.length))).toBe(21)));
  const stored=await(await page.request.get(`${fixture}/records`)).json();
  const rows=new Map<string,{occurred_at:string;created_at:string}>(stored.records.map((r:{notification_id:string;occurred_at:string;created_at:string})=>[r.notification_id,r]));
  const measured=(await Promise.all(pages.map(p=>p.evaluate(()=>((window as unknown as {notificationAcceptance:{renders:{id:string;rendered_at:number;signal_at:number}[]}}).notificationAcceptance.renders))))).flat().map(r=>{
   const record=rows.get(r.id)!;return {...r,triggered_at:Date.parse(record.occurred_at),stored_at:Date.parse(record.created_at),latency_ms:r.rendered_at-Date.parse(record.occurred_at)};
  });
  const ordered=measured.map(r=>r.latency_ms).sort((a,b)=>a-b);
  const result={...setup,...deadline,recovery_enabled:false,samples:measured.length,p99_ms:ordered[Math.ceil(ordered.length*.99)-1],max_ms:ordered.at(-1),failures:measured.filter(r=>r.latency_ms>3000).length,measurements:measured};
  await writeFile(testInfo.outputPath('notification-latency.json'),JSON.stringify(result,null,2));
  await testInfo.attach('notification-latency',{body:JSON.stringify(result),contentType:'application/json'});
  console.log(JSON.stringify({...result,measurements:undefined}));
  expect(result.samples).toBeGreaterThanOrEqual(200);expect(result.p99_ms).toBeLessThanOrEqual(3000);
  // An interrupted connection restores received state from the database.
  const connection=()=>pages[0].evaluate(()=>{const state=(window as unknown as {notificationAcceptance:{connectionErrors:number;connectionOpens:number}}).notificationAcceptance;return {errors:state.connectionErrors,opens:state.connectionOpens};});
  const before=await connection();
  await contexts[0].setOffline(true);
  await expect.poll(async()=>(await connection()).errors,{timeout:12000}).toBeGreaterThan(before.errors);
  await expect(pages[0].getByText('实时连接中断，正在重连。')).toHaveCount(0);
  await expect(pages[0].locator('.notification-card')).toHaveCount(21);
  await contexts[0].setOffline(false);
  await expect.poll(async()=>(await connection()).opens,{timeout:12000}).toBeGreaterThan(before.opens);
  await expect(pages[0].locator('.notification-card')).toHaveCount(21);
  const account=await(await contexts[0].request.get(`${base}/api/auth/session`)).json();
  await contexts[0].request.post(`${base}/api/auth/sign_out`,{headers:{'X-Serenita-Account-ID':account.account_id}});
  await expect(pages[0].locator('input[name=account]')).toBeVisible({timeout:15000});
  await expect(pages[0].locator('.notification-card')).toHaveCount(0);
 }finally{for(const context of contexts)await context.close();}
});
