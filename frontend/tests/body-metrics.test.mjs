import test from 'node:test';
import assert from 'node:assert/strict';
import {loadModule} from './helpers/load-module.mjs';
import {createElement} from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
const {range}=loadModule('features/bodyMetrics/bodyMetricPresentation.ts');
test('body metric calendar boundaries use local calendar dates',()=>{
 assert.deepEqual(range('2026-09-07','week',''),{after:'2026-09-07',before:'2026-09-13'});
 assert.deepEqual(range('2026-09-13','week',''),{after:'2026-09-07',before:'2026-09-13'});
 assert.deepEqual(range('2024-02-29','month',''),{after:'2024-02-01',before:'2024-02-29'});
 assert.deepEqual(range('2026-12-31','month',''),{after:'2026-12-01',before:'2026-12-31'});
 assert.deepEqual(range('2026-09-08','year',''),{after:'2026-01-01',before:'2026-12-31'});
 assert.deepEqual(range('2026-08-29','custom','2026-09-05'),{after:'2026-08-29',before:'2026-09-05'});
});
const {MetricChart}=loadModule('features/bodyMetrics/MetricChart.tsx');
function renderChart(buckets, overrides={}) {
 return renderToStaticMarkup(createElement(MetricChart, {daily:false,onRecord(){},series:{label:'摄入能量',unit:'kcal',source:'虚构演示数据',aggregation:'sum',points:[],buckets,...overrides}}));
}
function bucket(date,value,maximum=value) {
 return {date,value,minimum:0,maximum,secondary_value:null,record_ids:[date]};
}
function attributes(markup,tag,className) {
 return [...markup.matchAll(new RegExp(`<${tag}\\b[^>]*class="${className}"[^>]*>`, 'g'))].map(([element])=>Object.fromEntries([...element.matchAll(/([\w-]+)="([^"]*)"/g)].map(([,key,value])=>[key,value])));
}
test('cumulative charts scale to daily totals, including totals larger than any meal or interval',()=>{
 for(const count of [2,7,30,90,365]) {
  const buckets=Array.from({length:count},(_,i)=>bucket(new Date(Date.UTC(2026,0,i+1)).toISOString().slice(0,10),1940+i*39,620));
  const markup=renderChart(buckets);
  const bars=attributes(markup,'rect','bm-bar');
  assert.equal(bars.length,count);
  for(const bar of bars) {
   assert.ok(Number(bar.y)>=20,`daily total escapes the plot: ${bar.y}`);
   assert.ok(Number(bar.height)>=0);
   assert.ok(Math.abs(Number(bar.y)+Number(bar.height)-202)<1e-9);
  }
  assert.match(markup,/clip-path="url\(#/);
 }
});
test('zero and single-record charts have finite coordinates',()=>{
 for(const value of [0,1,1979]) {
  const markup=renderChart([bucket('2026-09-08',value)]);
  assert.doesNotMatch(markup,/NaN|Infinity/);
  const [bar]=attributes(markup,'rect','bm-bar');
  assert.ok(Number(bar.y)>=20&&Number(bar.y)<=202);
 }
});
test('blood pressure scale contains both plotted components',()=>{
 const markup=renderChart([{...bucket('2026-09-08',80,80),minimum:80,secondary_value:120}],{aggregation:'mean'});
 const path=attributes(markup,'path','bm-line bm-line-secondary')[0];
 const coords=path.d.split(' ');
 assert.ok(Number(coords[2])>=20&&Number(coords[2])<=202);
});
const routes=loadModule('app/routes.ts');
test('body metric routes keep member and category boundaries',()=>{
 const path=routes.bodyMetricPath('demo member','sleep');
 assert.equal(path,'/health/demo%20member/body-metrics/sleep');
 assert.equal(routes.isBodyMetricRoute(path),true);
 assert.equal(routes.bodyMetricCategory(path),'sleep');
 assert.equal(routes.isBodyMetricRoute('/health/demo/reports'),false);
 assert.equal(routes.isBodyMetricRoute('/health/demo/body-metrics/sleep/unexpected'),false);
});
