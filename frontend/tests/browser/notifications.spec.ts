import {expect,test} from '@playwright/test';
import {mockWorkspace} from '../helpers/workspace';

test.use({timezoneId:'America/Los_Angeles'});
for(const width of [1280,390])test(`global notifications, actions, targets and settings at ${width}px`,async({page})=>{
 await page.clock.install({time:new Date('2026-09-07T00:00:30Z')});
 await mockWorkspace(page);await page.setViewportSize({width,height:900});
 let fail=true;
 const preferences={notifications_enabled:false,medication_due_enabled:false,medication_expired_enabled:false,answer_completed_enabled:false};
 const items=[
  {notification_id:'one',member_id:'self',notification_type:'medication_due',title:'用药时间到了',message:'本人 · 药品一 1 粒',occurred_at:'2026-09-07T00:00:00Z',available_at:'2026-09-07T00:00:00Z',status:'pending',details:[{label:'成员',text:'本人'},{label:'药品',text:'药品一'}],target:{member_id:'self',resource_type:'medication_plan',resource_id:'plan-one'},actions:['read']},
  {notification_id:'two',member_id:'self',notification_type:'answer_completed',title:'回答已生成',message:'体检结果咨询',occurred_at:'2026-09-06T23:00:00Z',available_at:'2026-09-06T23:00:00Z',status:'pending',details:[{label:'聊天',text:'体检结果咨询'}],target:{member_id:null,resource_type:'conversation',resource_id:'chat-two'},actions:['read']},
 ];
 items.push(
  {...items[1],notification_id:'three',message:'已读聊天',occurred_at:'2026-09-07T00:00:15Z',status:'read',actions:[]},
  {...items[1],notification_id:'four',message:'较早聊天',occurred_at:'2026-09-05T00:00:00Z',status:'read',actions:[]},
 );
 items.reverse();
 await page.route('**/api/account-settings/notifications',route=>{
  if(route.request().method()==='PUT'){
   if(fail)return route.fulfill({status:503,json:{detail:{message:'通知设置未保存'}}});
   expect(Object.keys(route.request().postDataJSON())).toHaveLength(1);
   const changes=route.request().postDataJSON();
   if('notifications_enabled' in changes){
    preferences.medication_due_enabled=changes.notifications_enabled;
    preferences.medication_expired_enabled=changes.notifications_enabled;
    preferences.answer_completed_enabled=changes.notifications_enabled;
   }else Object.assign(preferences,changes);
   preferences.notifications_enabled=preferences.medication_due_enabled||preferences.medication_expired_enabled||preferences.answer_completed_enabled;
  }
  return route.fulfill({json:{...preferences,medication_due_enabled_since:null,medication_expired_enabled_since:null,answer_completed_enabled_since:null,notifications_enabled_since:null,notifications_updated_at:'2026-09-08T00:00:00Z'}});
 });
 await page.route(/\/api\/notifications\?/,route=>route.fulfill({json:{items:items.filter(i=>i.status===new URL(route.request().url()).searchParams.get('status')),next_cursor:null,errors:[]}}));
 await page.route('**/api/notifications/summary',route=>route.fulfill({json:{pending_count:items.filter(i=>i.status==='pending').length,errors:[]}}));
 await page.route('**/api/notifications/*/actions',route=>{
  const id=new URL(route.request().url()).pathname.split('/').at(-2)!;
  const item=items.find(i=>i.notification_id===id)!;item.status='read';item.actions=[];
  return route.fulfill({json:{notification_id:id,status:'read',available_at:item.available_at}});
 });
 await page.goto('/notifications');
 const center=page.getByRole('region',{name:'通知中心'});
 await expect(center.locator('.notification-card')).toHaveCount(4);
 await expect(center.getByRole('tab')).toHaveCount(0);
 await expect(page.getByText('实时连接中断，正在重连。')).toHaveCount(0);
 await expect(page.getByLabel('通知刷新异常')).toHaveCount(0);
 const order=()=>center.locator('.notification-card').evaluateAll(nodes=>nodes.map(node=>node.getAttribute('data-notification-id')));
 await expect.poll(order).toEqual(['one','two','three','four']);
 await expect(center.locator('time').first()).toHaveText('刚刚');
 await page.clock.fastForward(30_000);
 await expect(center.locator('time').first()).toHaveText('1分钟前');
 await expect(center.locator('.control-row-description').first()).toHaveText('本人 · 药品一 1 粒');
 await expect(center.getByRole('button',{name:/分钟后提醒/})).toHaveCount(0);
 const geometry=await center.evaluate(element=>{
  const main=element.closest('.patient-main')!.getBoundingClientRect();
  const toolbar=element.querySelector('.workspace-navigation-toolbar')!.getBoundingClientRect();
  const content=element.querySelector('.notification-list > .grouped-object-list')!.getBoundingClientRect();
  const maximum=parseFloat(getComputedStyle(element).getPropertyValue('--size-conversation-content'));
  return {main:{left:main.left,right:main.right,top:main.top},toolbar:{left:toolbar.left,right:toolbar.right,top:toolbar.top},content:{left:content.left,right:content.right,width:content.width},maximum};
 });
 expect(geometry.toolbar).toEqual(geometry.main);
 expect(geometry.content.width).toBeLessThanOrEqual(geometry.maximum);
 expect(Math.abs(geometry.content.left-geometry.main.left-(geometry.main.right-geometry.content.right))).toBeLessThan(1);
 await page.screenshot({path:`../artifacts/verification/notifications-${width}.png`,fullPage:true});
 await center.locator('.notification-card').first().getByRole('button',{name:'标为已读',exact:true}).click();
 await expect.poll(order).toEqual(['two','three','one','four']);
 const readCard=center.locator('[data-notification-id=one]');
 const colors=await readCard.evaluate(card=>({title:getComputedStyle(card.querySelector('.control-row-title')!).color,muted:getComputedStyle(card).getPropertyValue('--color-foreground-muted').trim(),size:getComputedStyle(card.querySelector('.control-row-title')!).fontSize,description:getComputedStyle(card.querySelector('.control-row-description')!).color}));
 expect(colors.title).toBe(colors.description);
 expect(colors.size).toBe('15px');
 await expect(readCard.getByRole('button',{name:'标为已读',exact:true})).toHaveCount(0);
 await center.getByRole('button',{name:'用药时间到了，查看详情'}).click();
 await expect(page).toHaveURL(/\/health\/self\/medications\/plans\/plan-one$/);
 await page.goto('/notifications');
 await center.locator('[data-notification-id=two]').getByRole('button',{name:'回答已生成，查看详情'}).click();
 await expect(page).toHaveURL(/\/chat\/chat-two$/);
 await page.goto('/setting');await page.getByRole('complementary',{name:'设置导航'}).getByRole('button',{name:'通知',exact:true}).click();
 const panel=page.getByRole('region',{name:'通知设置',exact:true});
 const toggle=panel.getByRole('switch',{name:'总通知',exact:true});
 await expect(toggle).toBeEnabled();await toggle.click();
 await expect(panel.getByRole('alert')).toContainText('通知设置未保存');await expect(toggle).not.toBeChecked();
 fail=false;await toggle.click();await expect(toggle).toBeChecked();
 const types=panel.getByRole('group',{name:'通知类型',exact:true});
 await expect(panel.getByRole('group',{name:'总通知',exact:true}).getByRole('switch')).toHaveCount(1);
 await expect(types.getByRole('switch')).toHaveCount(3);
 const due=types.getByRole('switch',{name:'用药提醒',exact:true});
 const expired=types.getByRole('switch',{name:'药品过期提醒',exact:true});
 const answer=types.getByRole('switch',{name:'回答已生成',exact:true});
 await due.click();await expect(due).not.toBeChecked();await expect(expired).toBeChecked();await expect(answer).toBeChecked();
 fail=true;await expired.click();await expect(panel.getByRole('alert')).toContainText('通知设置未保存');await expect(expired).toBeChecked();
 fail=false;await expired.click();await expect(expired).not.toBeChecked();
 await answer.click();await expect(answer).not.toBeChecked();await expect(toggle).not.toBeChecked();
 await toggle.click();await expect(toggle).toBeChecked();
 await expect(due).toBeChecked();await expect(expired).toBeChecked();await expect(answer).toBeChecked();
 await toggle.click();await expect(toggle).not.toBeChecked();
 await expect(due).not.toBeChecked();await expect(expired).not.toBeChecked();await expect(answer).not.toBeChecked();
 await expired.click();await expect(expired).toBeChecked();await expect(toggle).toBeChecked();
 await expect(due).not.toBeChecked();await expect(answer).not.toBeChecked();
 await page.reload();
 await page.getByRole('complementary',{name:'设置导航'}).getByRole('button',{name:'通知',exact:true}).click();
 await expect(panel.getByRole('switch',{name:'总通知',exact:true})).toBeChecked();
 await expect(due).not.toBeChecked();await expect(expired).toBeChecked();await expect(answer).not.toBeChecked();
 await page.screenshot({path:`../artifacts/verification/notification-type-settings-${width}.png`});
 await page.goto('/notifications');await expect(center.locator('.notification-card')).toHaveCount(4);
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth)).toBe(true);
});

test('combined notifications retain ordering across partial failures and both page cursors',async({page})=>{
 await mockWorkspace(page);
 let failRead=true;
 const item=(id:string,status:string,date:string)=>({notification_id:id,notification_type:'answer_completed',title:id,message:'体检结果咨询',occurred_at:date,status,details:[],target:{member_id:'self',resource_type:'conversation',resource_id:id},actions:status==='pending'?['read']:[]});
 const pending=[item('pending-new','pending','2026-09-06T12:00:00Z'),item('pending-old','pending','2026-09-04T12:00:00Z')];
 const read=[item('read-new','read','2026-09-07T12:00:00Z'),item('read-old','read','2026-09-05T12:00:00Z')];
 const requests:string[]=[];
 await page.route(/\/api\/notifications\?/,route=>{
  const query=new URL(route.request().url()).searchParams,status=query.get('status')!,cursor=query.get('cursor');
  requests.push(`${status}:${cursor||'first'}`);
  if(status==='read'&&failRead)return route.fulfill({status:503,json:{detail:{message:'已读通知读取失败'}}});
  const items=status==='pending'?pending:read;
  return route.fulfill({json:{items:cursor?items:[items[0]],next_cursor:cursor?null:`${status}-next`,errors:[]}});
 });
 await page.goto('/notifications');
 const center=page.getByRole('region',{name:'通知中心'});
 const order=()=>center.locator('.notification-card').evaluateAll(nodes=>nodes.map(node=>node.getAttribute('data-notification-id')));
 await expect.poll(order).toEqual(['pending-new']);
 await expect(center.getByRole('alert')).toContainText('已读通知读取失败');
 await center.getByRole('button',{name:'继续加载',exact:true}).click();
 await expect.poll(order).toEqual(['pending-new','pending-old']);
 await expect(center.getByRole('alert')).toContainText('已读通知读取失败');
 failRead=false;
 await center.getByRole('button',{name:'重试',exact:true}).click();
 await expect.poll(order).toEqual(['pending-new','read-new']);
 await expect(center.getByRole('alert')).toHaveCount(0);
 await center.getByRole('button',{name:'继续加载',exact:true}).click();
 await expect.poll(order).toEqual(['pending-new','pending-old','read-new']);
 await center.getByRole('button',{name:'继续加载',exact:true}).click();
 await expect.poll(order).toEqual(['pending-new','pending-old','read-new','read-old']);
 expect(requests.slice(-2)).toEqual(['pending:pending-next','read:read-next']);
 await expect(center.getByRole('button',{name:'继续加载',exact:true})).toHaveCount(0);
});


test('expired medication notification opens its exact batch', async({page})=>{
 await mockWorkspace(page);
 const item={notification_id:'expired-batch',member_id:'self',notification_type:'medication_expired',title:'药品已过期',message:'本人 · 药品一 · 有效期至 2026-09-01',occurred_at:'2026-09-02T00:00:00Z',status:'pending',details:[],target:{member_id:'self',resource_type:'medication_batch',resource_id:'batch-one',medication_id:'drug-one'},actions:['read']};
 await page.route(/\/api\/notifications\?/,route=>route.fulfill({json:{items:new URL(route.request().url()).searchParams.get('status')==='pending'?[item]:[],next_cursor:null,errors:[]}}));
 await page.goto('/notifications');
 await page.getByRole('button',{name:'药品已过期，查看详情'}).click();
 await expect(page).toHaveURL(/\/health\/self\/medications\/catalog\/drug-one\/batches\/batch-one$/);
});
