import test from 'node:test';
import assert from 'node:assert/strict';
import {loadModule} from './helpers/load-module.mjs';
const {ResourceDraft}=loadModule('utils/resourceDraft.ts');
const deferred=()=>{let resolve,reject;const promise=new Promise((a,b)=>{resolve=a;reject=b;});return{promise,resolve,reject};};

test('slow acknowledgement preserves and then submits text entered during the request',async()=>{
 const draft=new ResourceDraft('saved');const first=deferred(),second=deferred(),calls=[];
 draft.update('first');const saved=draft.flush(value=>{calls.push(value);return calls.length===1?first.promise:second.promise;});
 await Promise.resolve();draft.update('second');draft.receive('background refresh',true);
 assert.equal(draft.snapshot().draft,'second');assert.equal(draft.snapshot().submitted,'first');
 first.resolve('first');await Promise.resolve();await Promise.resolve();
 assert.equal(draft.snapshot().draft,'second');assert.deepEqual(calls,['first','second']);
 second.resolve('second');assert.equal(await saved,true);assert.equal(draft.snapshot().dirty,false);
});

test('failure keeps the draft and blocks navigation until an explicit retry succeeds',async()=>{
 const draft=new ResourceDraft('saved');draft.update('unsaved');
 assert.equal(await draft.flush(async()=>{throw new Error('connection lost');}),false);
 assert.equal(draft.snapshot().draft,'unsaved');assert.equal(draft.snapshot().error,'connection lost');
 draft.receive('updated by another page');assert.equal(draft.snapshot().draft,'unsaved');
 assert.equal(await draft.flush(async value=>value),true);assert.equal(draft.snapshot().server,'unsaved');
});

test('a refresh during an untouched edit does not turn old text into a write',async()=>{
 const draft=new ResourceDraft('original');draft.receive('external change',true);
 assert.equal(draft.snapshot().draft,'original');assert.equal(draft.snapshot().dirty,false);
 assert.equal(await draft.flush(async()=>assert.fail('an untouched editor wrote stale content')),true);
 draft.cancel();assert.equal(draft.snapshot().draft,'external change');
});

test('composition postpones a requested flush until committed text is available',async()=>{
 const draft=new ResourceDraft('saved');draft.composition(true);draft.update('pin');let calls=0;
 const pending=draft.flush(async value=>{calls++;assert.equal(value,'拼音');return value;});
 await Promise.resolve();assert.equal(calls,0);draft.update('拼音');draft.composition(false);
 assert.equal(await pending,true);assert.equal(calls,1);
});

test('reverting while a write is pending still saves the final user intent',async()=>{
 const draft=new ResourceDraft('original');const first=deferred(),calls=[];
 draft.update('temporary');const pending=draft.flush(value=>{calls.push(value);return calls.length===1?first.promise:Promise.resolve(value);});
 await Promise.resolve();draft.update('original');first.resolve('temporary');
 assert.equal(await pending,true);assert.deepEqual(calls,['temporary','original']);
});
