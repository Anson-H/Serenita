import {expect,test} from '@playwright/test';
import {mockWorkspace} from '../helpers/workspace';
import {expectSelectionGaps,expectSelectionReplacement} from '../helpers/selectionSpacing';

for(const width of [1280,390]) {
  test(`sidebar selection keeps compact outer spacing at ${width}px`,async({page},testInfo)=>{
    await page.setViewportSize({width,height:900});await mockWorkspace(page);
    await page.route('**/api/conversations',route=>route.fulfill({json:{sessions:[{session_id:'chat',title:'你好问候',member_id:'self',member_name:'本人',access_state:'available',is_pinned:false,created_at:'2026-09-07T00:00:00Z',last_active_at:'2026-09-07T00:00:00Z',pending_turn_status:null,queued_input_count:0}],has_more:false,next_cursor:null}}));
    await page.goto('/reports');
    if(width===390)await page.getByRole('button',{name:'展开侧边栏',exact:true}).click();
    await page.locator('.conversation-title-button').click({button:'right'});
    await page.getByRole('menuitem',{name:'多选',exact:true}).click();
    await expect(page.locator('.report-filter-bar')).toBeVisible();
    await expect(page.locator('.report-library .list-selection-heading')).toHaveCount(0);
    await expectSelectionGaps(page.locator('.global-nav > .list-selection-heading'),page.locator('.health-member-nav'),page.locator('.conversation-list-stage'));
    await page.locator('.sidebar-content').screenshot({path:testInfo.outputPath(`sidebar-${width}.png`)});
  });

  test(`favorites and lab catalogs share selection spacing at ${width}px`,async({page},testInfo)=>{
    await page.setViewportSize({width,height:900});await mockWorkspace(page);
    await page.route('**/api/favorites',route=>route.fulfill({json:{favorites:[{favorite_id:'one',title:'复诊记录',source_type:'message',source_id:'message',member_id:'self',member_name:'本人',content_summary:'已保存的内容',tags:[],created_at:'2026-09-01T00:00:00Z'}],has_more:false,next_cursor:null}}));
    await page.goto('/favorites');await page.getByRole('button',{name:'多选收藏',exact:true}).click();
    await expectSelectionGaps(page.locator('.favorite-list-panel > .list-selection-heading'),page.locator('.favorites-list-toolbar'),page.locator('.favorite-selection-row').first());
    await page.locator('.favorite-list-panel').screenshot({path:testInfo.outputPath(`favorites-${width}.png`)});
    await page.route('**/api/account-settings/lab-dictionary',route=>route.fulfill({json:{dictionary_revision:'1',summary:{item_count:1,category_count:1,relation_count:0},items:[{item_id:'one',item_name_zh:'测试指标',aliases:[],primary_category_name:'测试分类',related_category_names:[],usage_by_category:[],result_count:0,report_count:0}],categories:[{category_name:'测试分类',item_count:1,primary_item_count:1,related_item_count:0,result_count:0,report_count:0}],relations:[]}}));
    for(const title of ['检验分类目录','检验指标目录']){
      await page.goto('/setting');await page.getByRole('button',{name:title,exact:true}).click();
      const listY=(await page.locator('.dictionary-grouped-list').boundingBox())!.y;
      await page.locator('.dictionary-entity-row').first().click({button:'right'});
      await page.getByRole('menuitem',{name:'多选',exact:true}).click();
      await expectSelectionReplacement(page.locator('.dictionary-list-body .list-selection-heading'),page.locator('.dictionary-list-tools'));
      expect((await page.locator('.dictionary-grouped-list').boundingBox())!.y).toBeCloseTo(listY,0);
      const count=page.locator('.dictionary-entity-list > .object-list-count');
      const gap=await count.evaluate(node=>node.getBoundingClientRect().top-node.previousElementSibling!.getBoundingClientRect().bottom);
      expect(gap).toBeCloseTo(15,0);
      await page.locator('.dictionary-list-body').screenshot({path:testInfo.outputPath(`${title}-${width}.png`)});
      await page.locator('.dictionary-list-body .list-selection-heading button').first().focus();
      await page.keyboard.press('Escape');
      await expect(page.locator('.dictionary-list-tools')).toBeVisible();
      await expect(page.locator('.dictionary-list-body .list-selection-heading')).toHaveCount(0);
    }
  });
}
