import assert from 'node:assert/strict';
import test from 'node:test';
import {loadModule} from './helpers/load-module.mjs';
import {hookRenderer} from './helpers/hook-renderer.mjs';
const tick=()=>new Promise(resolve=>setImmediate(resolve));
const deferred=()=>{let resolve,reject;const promise=new Promise((yes,no)=>{resolve=yes;reject=no;});return {promise,resolve,reject};};
function setup(options){
  const renderer=hookRenderer(),timers=new Map(),barriers=new Set();let timerId=0;
  const {useAutosaveResource}=loadModule('utils/useAutosaveResource.ts',{window:{setTimeout:cb=>{timers.set(++timerId,cb);return timerId;},clearTimeout:id=>timers.delete(id)}},{react:renderer.react,'./useActiveScope':{useActiveScope:()=>()=>true},'./pendingNavigation':{registerNavigationSave:cb=>{barriers.add(cb);return()=>barriers.delete(cb);}}});
  let props={resourceKey:'member:resource',server:{title:'saved'},enabled:true,...options};
  const render=next=>{props={...props,...next};return renderer.render(()=>useAutosaveResource(props));};
  render();
  return {render,get editor(){return renderer.value;},timers,fire:async()=>{const pending=[...timers.values()];timers.clear();for(const cb of pending)cb();await tick();render();},navigate:async()=>{for(const barrier of barriers)if(!await barrier())return false;return true;},unmount:renderer.unmount};
}

test('autosave failure retains the draft without automatic retries; editing, explicit retry and permission loss obey the shared lifecycle',async()=>{
  let writes=0,fail=true;const h=setup({save:async value=>{writes++;if(fail)throw Error('service unavailable');return value;}});
  h.editor.change({title:'unsaved'});h.render();assert.equal(h.timers.size,1);await h.fire();
  assert.equal(writes,1);assert.equal(h.editor.error,'service unavailable');assert.equal(h.editor.draft.title,'unsaved');assert.equal(h.timers.size,0);
  h.render();await h.fire();assert.equal(writes,1);
  assert.equal(await h.editor.flushOnBlur(),false);h.render();assert.equal(writes,1);assert.equal(h.editor.error,"service unavailable");
  assert.equal(await h.editor.flush(),false);h.render();assert.equal(writes,2);assert.equal(h.timers.size,0);
  h.editor.change({title:'new edit'});h.render();assert.equal(h.timers.size,1);fail=false;await h.fire();assert.equal(writes,3);assert.equal(h.editor.dirty,false);
  h.editor.change({title:'permission lost draft'});h.render({enabled:false});assert.equal(h.timers.size,0);assert.equal(await h.navigate(),true);assert.equal(writes,3);assert.equal(h.editor.draft.title,'permission lost draft');h.unmount();
});

test('navigation waits for deletion and a failed delete preserves the unsaved resource on the current page',async()=>{
  const gate=deferred();let removed=0,writes=0;
  const h=setup({save:async value=>{writes++;return value;},remove:()=>gate.promise,onRemoved:()=>removed++});
  h.editor.change({title:'unsaved'});h.render();const deletion=h.editor.remove();h.render();await tick();
  let navigationSettled=false;const navigation=h.navigate().then(value=>{navigationSettled=true;return value;});await tick();
  assert.equal(navigationSettled,false);assert.equal(h.editor.controller.snapshot().draft.title,'unsaved');gate.reject(Error('delete unavailable'));
  assert.equal(await deletion,false);assert.equal(await navigation,false);h.render();assert.equal(h.editor.draft.title,'unsaved');assert.equal(h.timers.size,0);assert.equal(writes,0);assert.equal(removed,0);h.unmount();
});

test('successful deletion waits for the running save, discards queued changes and can navigate from its completion callback',async()=>{
  const save=deferred(),deletion=deferred(),events=[];let ownNavigation;
  const h=setup({save:async value=>{events.push('save');await save.promise;return value;},remove:async()=>{events.push('delete');await deletion.promise;},onRemoved:()=>{ownNavigation=h.navigate();}});
  h.editor.change({title:'first'});const saving=h.editor.flush();await tick();h.render();h.editor.change({title:'second'});h.render();
  const removing=h.editor.remove();await tick();assert.deepEqual(events,['save']);save.resolve();await saving;await tick();assert.deepEqual(events,['save','delete']);
  const leaving=h.navigate();deletion.resolve();assert.equal(await removing,true);assert.equal(await leaving,true);assert.equal(await ownNavigation,true);assert.deepEqual(events,['save','delete']);h.unmount();
});
