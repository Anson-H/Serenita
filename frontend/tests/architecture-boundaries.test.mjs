import assert from 'node:assert/strict';
import test from 'node:test';
import { loadModule } from './helpers/load-module.mjs';
const noop = () => {};
const ref = current => ({ current });
const deferred = () => { let resolve, reject; const promise = new Promise((yes, no) => { resolve=yes; reject=no; }); return { promise, resolve, reject }; };
const tick = () => new Promise(resolve => setImmediate(resolve));

test('failed report deletion readback cannot replace a later selected report', async () => {
  const read = deferred();
  let reads = 0;
  const { ReportDetailState } = loadModule('features/reports/model/detail.ts');
  const detail = new ReportDetailState('m', {
    read: async (_member, id) => ++reads === 2 ? read.promise : { report_id: id, member_id: 'm' },
    isCurrent: () => true, beforeNavigate: async () => true, onError: noop, onOpened: noop,
  });
  await detail.open('a');
  const { ReportCollectionActions } = loadModule('features/reports/model/collection.ts', {}, {
    '../../../api/client': { apiClient: { deleteReport: async () => { throw Error('delete failed'); } } }
  });
  const actions = new ReportCollectionActions(detail, {
    canEdit: () => true, isCurrent: () => true, onChanged: async () => {}, onDeleted: noop,
    onReportCleared: noop, onError: noop, onMessage: noop,
  });
  const pending = actions.deleteReports(['a']); await tick();
  await detail.open('b');
  read.resolve({ report_id: 'a', member_id: 'm' });
  assert.deepEqual(await pending, ['a']);
  assert.equal(detail.snapshot().selectedReport.report_id, 'b');
});

test('report publication rejects details belonging to another member or selection', async () => {
  const { ReportDetailState } = loadModule('features/reports/model/detail.ts');
  const detail = new ReportDetailState('m', {
    read: async (_member, id) => ({ report_id: id, member_id: 'm' }),
    isCurrent: () => true, beforeNavigate: async () => true, onError: noop, onOpened: noop,
  });
  await detail.open('b');
  assert.equal(detail.apply({ report_id: 'a', member_id: 'm' }), false);
  assert.equal(detail.apply({ report_id: 'b', member_id: 'other' }), false);
  assert.equal(detail.snapshot().selectedReport.report_id, 'b');
  assert.equal(detail.snapshot().selectedReport.member_id, 'm');
});

test('favorite detail read preserves saved tags and the next addition uses those tags', async () => {
  const { FavoriteEntities }=loadModule('features/favorites/favoriteEntities.ts'); const entities=new FavoriteEntities();
  const original={favorite_id:'f',tags:['old']}; entities.updateList([original]);
  const revision=entities.tagRevision('f'); entities.updateList([{...original,tags:['old','saved']}]);
  entities.acceptDetail({...original,content:'detail'},revision);
  const writes=[];
  const {createFavoriteTagActions}=loadModule('features/favorites/favoriteTagActions.ts',{}, {'../../api/client':{apiClient:{updateFavorite:async(id,tags)=>{writes.push(tags);return {...original,tags};}}},'../../components/StatusNotificationCenter':{showStatusNotification:noop}});
  const actions=createFavoriteTagActions(new Proxy({favorites:[original],favoriteDetail:original,getFavorite:entities.get,
    pendingFavoriteTagsRef:ref(new Map()),favoriteTagSavePromisesRef:ref(new Map()),favoriteWorkspaceRevisionRef:ref(1),
    setFavorites:entities.updateList,setFavoriteDetail:entities.updateDetail}, {get:(value,key)=>key in value ? value[key] : noop}));
  actions.appendFavoriteTag('f','next'); await actions.flushFavoriteTags('f');
  assert.deepEqual(writes,[['old','saved','next']]); assert.deepEqual(entities.detail().tags,writes[0]);
});

test('a catalog response started before a default write is reread without publishing the old default', async () => {
  const {ModelCatalogState}=loadModule('features/modelConfiguration/useModelCatalog.ts'); const reads=[];
  const state=new ModelCatalogState(()=>{const gate=deferred(); reads.push(gate);return gate.promise;});
  const pending=state.refresh(); state.update(current=>({...current,defaults:{...current.defaults,chat:{model_id:'new'}}}));
  reads[0].resolve({...state.snapshot(),defaults:{chat:{model_id:'old'}}}); await tick();
  assert.equal(state.snapshot().defaults.chat.model_id,'new'); assert.equal(reads.length,2);
  reads[1].resolve({...state.snapshot(),status:'ready'}); await pending; assert.equal(state.snapshot().defaults.chat.model_id,'new');
});

test('provider A remote models cannot populate B or be added under B', async () => {
  const gate=deferred(); let generation=1, models=[], adds=0;
  const {createModelSettingsActions}=loadModule('features/settings/modelSettingsActions.ts',{}, {'../../api/client':{apiClient:{fetchProviderModels:()=>gate.promise,addModel:async()=>adds++}},'../../components/StatusNotificationCenter':{showStatusNotification:noop}});
  const actions=createModelSettingsActions(new Proxy({selectedProvider:{provider_id:'a'},selectedDraft:{},beginRemoteRead:()=>{const own=generation;return()=>own===generation;},isRemoteModelCurrent:()=>false,autoSaveProviderDraft:async()=>({}),setRemoteModels:next=>models=next}, {get:(value,key)=>key in value ? value[key] : noop}));
  const read=actions.openAddModelModal(); await tick(); generation++;
  const stale={remote_model_id:'from-a'}; gate.resolve({models:[stale]}); await read; await actions.addRemoteModel(stale);
  assert.deepEqual(models,[]); assert.equal(adds,0);
});

test('changing report detail during a favorite request still applies the favorite and releases busy state', async () => {
  const gate = deferred(); let busy = false, favorites = [];
  const { ReportDetailState } = loadModule('features/reports/model/detail.ts');
  const detail = new ReportDetailState('m', {
    read: async (_member, id) => ({ report_id: id, member_id: 'm' }),
    isCurrent: () => true, beforeNavigate: async () => true, onError: noop, onOpened: noop,
  });
  await detail.open('a');
  const { createReportFavoriteActions } = loadModule('features/reports/model/favorites.ts', {}, {
    '../../../api/client': { apiClient: { createFavoriteSource: () => gate.promise } }
  });
  const actions = createReportFavoriteActions({
    memberId: 'm', ...detail.snapshot(), reportFavorite: null, favoritingReport: false,
    favoritedReportIds: new Set(), isCurrentScope: () => true,
    setActionError: noop, setActionMessage: noop,
    setFavoritingReport: value => busy = value, setFavorites: next => favorites = next(favorites),
  });
  const pending = actions.toggleReportFavorite(); assert.equal(busy, true);
  await detail.open('b');
  gate.resolve({ favorite_id: 'f', source_id: 'a' });
  assert.equal(await pending, true); assert.equal(busy, false);
  assert.equal(favorites[0].source_id, 'a'); assert.equal(detail.snapshot().selectedReportId, 'b');
});

function uploadHarness(upload, read = async session_id=>({session_id})) {
  const {ConversationDraftStore}=loadModule('features/conversations/conversationDraftStore.ts');const draftStore=new ConversationDraftStore(); let selected=null,detail=null;
  const {useConversationAttachments}=loadModule('features/conversations/useConversationAttachments.ts',{}, {react:{useEffect:noop},'../../utils/useActiveScope':{useActiveScope:()=>()=>true},'../members/MemberProvider':{useMembers:()=>({activeMemberId:'m'})},'../../api/client':{apiClient:{uploadContextResource:upload,getConversation:read}}});
  const hook=useConversationAttachments({draftStore,currentSessionId:null,conversationDetail:null,selectedModelId:'model',selectedModelFileMimeTypes:['image/png'],attachmentCapabilitiesReady:true,uploadedResourcesLength:0,setComposerError:noop,setConversationDetail:value=>detail=value,setCurrentSessionId:value=>selected=value,setUploadedResources:noop,setUploadingResources:noop});
  return {draftStore,hook,selected:()=>selected,detail:()=>detail};
}

test('late upload belongs to the original draft and saved home draft receives its completed state',async()=>{
  const gate=deferred(),h=uploadHarness(()=>gate.promise),original=h.draftStore.capture();
  const pending=h.hook.handleFileUpload({currentTarget:{files:[{name:'a.png'}],value:''}}); await tick();
  assert.equal(original.value.uploadingResources.length,1); h.draftStore.reset();
  gate.resolve({session_id:'uploaded',resource:{resource_id:'f',original_filename:'a.png'}});await pending;
  assert.equal(h.selected(),null);assert.equal(h.draftStore.snapshot().uploadedResources.length,0);
  h.draftStore.restore(original);assert.equal(h.draftStore.snapshot().uploadedResources.length,1);assert.equal(h.draftStore.snapshot().uploadingResources.length,0);assert.equal(original.sessionId,'uploaded');
});

test('two simultaneous file selections share the upload-created session',async()=>{
  const first=deferred(),sessions=[]; const h=uploadHarness(async(_member,session,_file)=>{sessions.push(session);return sessions.length===1?first.promise:{session_id:'one',resource:{resource_id:'second'}};});
  const a=h.hook.uploadFiles([{name:'a'}]),b=h.hook.uploadFiles([{name:'b'}]);await tick();assert.deepEqual(sessions,[null]);
  first.resolve({session_id:'one',resource:{resource_id:'first'}});await Promise.all([a,b]);assert.deepEqual(sessions,[null,'one']);
});

test('queue restoration locks the draft and keeps nonfile resources with its session across navigation',async()=>{
  const {ConversationDraftStore}=loadModule('features/conversations/conversationDraftStore.ts'),store=new ConversationDraftStore();
  const gate=deferred();let current=true,calls=0;
  const {createConversationQueueActions}=loadModule('features/conversations/conversationQueueActions.ts',{}, {'../../api/client':{apiClient:{restoreQueuedInputToDraft:()=>{calls++;return gate.promise;}}}});
  const actions=createConversationQueueActions(new Proxy({draftStore:store,currentSessionId:'s',composerText:'',uploadedResources:[],uploadingResources:[],annotatedContexts:[],isCurrentScope:()=>current}, {get:(value,key)=>key in value ? value[key] : noop}));
  const pending=actions.restoreQueuedInputToDraft('i');store.update('composerText','must not overwrite restored text');await actions.restoreQueuedInputToDraft('i');assert.equal(calls,1);
  current=false;store.reset();gate.resolve({queued_input:{input_id:'i',content:'restored',context_resources:[{resource_type:'report',resource_id:'report'}]},queued_inputs:[]});await pending;
  assert.equal(store.snapshot().composerText,'');store.openSession('s');assert.equal(store.snapshot().composerText,'restored');assert.equal(store.snapshot().restoring,false);assert.equal(store.snapshot().contextResources[0].resource_id,'report');
});

test('report task retry after all files uploaded resubmits without uploading duplicate files',async()=>{
  let uploads=0,submits=0;
  const {useAttachmentTask}=loadModule('features/conversations/useAttachmentTask.ts',{}, {react:{useRef:ref}});
  const task=useAttachmentTask({scopeKey:'m:reports',uploadFiles:async(files,_id,batch)=>{uploads++;batch.onUploaded('s',{resource_id:'f',original_filename:files[0].name});},submitMessage:async()=>++submits===1?undefined:{session_id:'s'}});
  const files=[{name:'report.pdf'}];await assert.rejects(task(files,'m','导入医疗报告'),/未发送/);await task(files,'m','导入医疗报告');assert.equal(uploads,1);assert.equal(submits,2);
});

test('deleting a resource stops queued changes after the running save and exposes a clean navigation draft',async()=>{
  const {ResourceDraft}=loadModule('utils/resourceDraft.ts'),draft=new ResourceDraft({name:'old'}),gate=deferred(),writes=[];
  draft.update({name:'first'});const pending=draft.flush(async value=>{writes.push(value.name);await gate.promise;return value;});await tick();
  draft.update({name:'second'});draft.pause();gate.resolve();await draft.settled();await pending;assert.deepEqual(writes,['first']);
  const unsaved=draft.snapshot().draft;draft.cancel();assert.equal(await draft.flush(async()=>{throw Error('must not write while deleting');}),true);
  draft.resume();draft.update(unsaved);assert.equal(draft.snapshot().draft.name,'second');assert.equal(draft.snapshot().dirty,true);
});

test('plan editor identity uses the plan id even when a linked medication id is present',()=>{
  const {itemId}=loadModule('features/medications/medicationPresentation.ts');assert.equal(itemId({medication_id:'drug',medication_plan_id:'plan'},'plan'),'plan');assert.equal(itemId({medication_id:'drug'},'medication'),'drug');
});

test('permanent stream 404 stops immediately, clears subscription and exposes the HTTP failure',async()=>{
  const {ApiRequestError}=loadModule('api/request.ts');const error=new ApiRequestError('stream missing',404,null);
  let calls=0,displayed='',refreshes=0;const activeStreamRef=ref(null);
  const {useConversationStreamController,canReconnectConversationStream}=loadModule('features/conversations/useConversationStreamController.ts',{window:globalThis},{
    '../../api/request':{ApiRequestError},'../../api/client':{apiClient:{streamConversation:async()=>{calls++;throw error;}}},
    '../../components/StatusNotificationCenter':{showStatusNotification:noop},'./thinking':{isAbortError:()=>false,thinkingModeLabel:noop}
  });
  const controller=useConversationStreamController({activeStreamRef,openConversation:async()=>true,onThinkingModeChanged:noop,onTurnSettled:noop,refreshConversations:async()=>refreshes++,setActiveStreamTurnId:noop,setCancellingTurnId:noop,setComposerError:value=>displayed=value,setConversationDetail:noop,setConversations:noop});
  await assert.rejects(controller.startResponseStream({session_id:'s',stream_id:'missing',turn_id:'t',final_assistant_message_id:'a'}),/stream missing/);
  assert.equal(calls,1);assert.equal(activeStreamRef.current,null);assert.equal(displayed,'stream missing');assert.equal(refreshes,1);
  assert.equal(canReconnectConversationStream(new ApiRequestError('busy',429,null)),true);assert.equal(canReconnectConversationStream(new ApiRequestError('timeout',408,null)),true);assert.equal(canReconnectConversationStream(new ApiRequestError('server',503,null)),true);
});

test('uploaded draft is associated before a delayed detail read and that read cannot replace a submitted conversation',async()=>{
  const gate=deferred(),h=uploadHarness(async()=>({session_id:'uploaded',resource:{resource_id:'f'}}),()=>gate.promise),draft=h.draftStore.capture();
  const upload=h.hook.handleFileUpload({currentTarget:{files:[{name:'a.png'}],value:''}});await tick();
  assert.equal(h.selected(),'uploaded');assert.equal(draft.sessionId,'uploaded');assert.equal(h.draftStore.snapshot().uploadingResources.length,0);
  h.draftStore.complete(draft,'uploaded');gate.resolve({session_id:'uploaded',records:[]});await upload;assert.equal(h.detail(),null);assert.equal(draft.valid,false);assert.equal(h.draftStore.snapshot().uploadedResources.length,0);
});

test('deleting a conversation invalidates its draft so the next upload starts a new session',async()=>{
  const targets=[],h=uploadHarness(async(_member,session)=>{targets.push(session);return {session_id:'new-session',resource:{resource_id:'new'}};});
  const old=h.draftStore.capture();h.draftStore.associate(old,'deleted');h.draftStore.update('composerText','old unsent text');
  const {createConversationListActions}=loadModule('features/conversations/conversationListActions.ts',{}, {'../../api/client':{apiClient:{deleteConversation:async()=>{}}},'../../components/StatusNotificationCenter':{showStatusNotification:noop}});
  const actions=createConversationListActions(new Proxy({onDeletedSessions:h.draftStore.forgetSessions,isCurrentScope:()=>true,visibleConversationRef:ref({currentSessionId:'deleted'}),refreshConversations:async()=>{}},{get:(value,key)=>key in value?value[key]:noop}));
  assert.equal(await actions.deleteConversationFromSidebar('deleted'),true);assert.equal(old.valid,false);assert.equal(h.draftStore.snapshot().composerText,'');
  await h.hook.uploadFiles([{name:'new.png'}]);assert.deepEqual(targets,[null]);
});

test('a failed chat default change reloads the shared catalog and restores the saved selection',async()=>{
  const {hookRenderer}=await import('./helpers/hook-renderer.mjs');const renderer=hookRenderer();
  const old={model_id:'old',model_type:'generation',thinking_modes:['default']},next={...old,model_id:'next'};
  let catalog={models:[old,next],defaults:{chat:old},status:'ready',error:''},refreshes=0,error='';
  const {useConversationModelControl}=loadModule('features/conversations/useConversationModelControl.ts',{}, {react:renderer.react,'../../api/client':{apiClient:{updateModelDefaults:async()=>{throw Error('default save failed');}}}});
  const render=()=>renderer.render(()=>useConversationModelControl({composerModelControlRef:ref(null),modelCatalog:catalog,setComposerError:value=>error=value,setModelCatalog:value=>{catalog=typeof value==='function'?value(catalog):value;},refreshModelCatalog:async()=>{refreshes++;catalog={...catalog,defaults:{chat:old}};}}));
  const control=render();await control.chooseSessionModel('next');assert.equal(render().selectedModelId,'old');assert.equal(refreshes,1);assert.equal(error,'default save failed');renderer.unmount();
});

test('a conversation deleted after navigation still invalidates its saved draft without clearing the new visible page',async()=>{
 const {ConversationDraftStore}=loadModule('features/conversations/conversationDraftStore.ts'),store=new ConversationDraftStore();
 const deleted=store.capture();store.associate(deleted,'deleted');store.update('composerText','old draft');store.reset();store.update('composerText','new visible draft');let clears=0;
 const {createConversationListActions}=loadModule('features/conversations/conversationListActions.ts',{}, {'../../api/client':{apiClient:{deleteConversation:async()=>{}}},'../../components/StatusNotificationCenter':{showStatusNotification:noop}});
 const actions=createConversationListActions(new Proxy({onDeletedSessions:store.forgetSessions,isCurrentScope:()=>false,visibleConversationRef:ref({currentSessionId:'new'}),setCurrentSessionId:()=>clears++,refreshConversations:async()=>{}},{get:(value,key)=>key in value?value[key]:noop}));
 await actions.deleteConversationFromSidebar('deleted');assert.equal(deleted.valid,false);assert.equal(store.snapshot().composerText,'new visible draft');assert.equal(clears,0);
});
