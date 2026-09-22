import {useEffect,useRef,useState,type ReactNode} from 'react';
import {readNotifications,actNotification,type NotificationItem,type NotificationStatus,type NotificationAction} from '../../api/notificationApi';
import {WorkspaceToolbar} from '../../components/WorkspaceToolbar';
import {EmptyState} from '../../components/EmptyState';
import {GroupedList} from '../../components/GroupedList';
import {ControlRowContent} from '../../components/ControlRowContent';
import {CheckIcon} from '../../components/icons';
import {notificationTime,notificationTimeRefreshDelay,orderedNotifications} from './notificationPresentation';
import {medicationBatchPath,medicationPath,chatPathForSession,type RoutePath} from '../../app/routes';
import {useNotifications} from './NotificationProvider';
import '../../styles/notifications.css';
export function NotificationWorkspace({onNavigate,sidebarToggle}:{onNavigate:(path:RoutePath)=>void;sidebarToggle:ReactNode}){
  const notifications=useNotifications();
  const [items,setItems]=useState<NotificationItem[]>([]);
  const [cursors,setCursors]=useState<Record<NotificationStatus,string|null>>({pending:null,read:null}),[error,setError]=useState(''),[loading,setLoading]=useState(false),[busy,setBusy]=useState<string|null>(null);
  const [listErrors,setListErrors]=useState<Partial<Record<NotificationStatus,string>>>({});
  const feedback=[...new Set([error,listErrors.pending,listErrors.read,notifications.error].filter(Boolean))].join(' ');
  const generation=useRef(0),refreshList=useRef<()=>void>(()=>{});
  const [now,setNow]=useState(Date.now);
  useEffect(()=>{
    if(!items.length)return;
    const delay=Math.min(60_000,...items.map(item=>notificationTimeRefreshDelay(item.occurred_at,Date.now())));
    const timer=window.setTimeout(()=>setNow(Date.now()),delay);
    const refresh=()=>setNow(Date.now());
    window.addEventListener('focus',refresh);
    document.addEventListener('visibilitychange',refresh);
    return()=>{window.clearTimeout(timer);window.removeEventListener('focus',refresh);document.removeEventListener('visibilitychange',refresh);};
  },[items,now]);
  useEffect(()=>{
    const controller=new AbortController();let active=true,running=false,dirty=false;
    async function refresh(){
      dirty=true;if(running)return;running=true;
      try{while(active&&dirty){
        dirty=false;const current=++generation.current;setLoading(true);setCursors({pending:null,read:null});
        const statuses=['pending','read'] as const;
        const results=await Promise.allSettled(statuses.map(status=>readNotifications(status,null,controller.signal)));
        if(active&&current===generation.current){
          const nextItems:NotificationItem[]=[],nextCursors:Record<NotificationStatus,string|null>={pending:null,read:null},errors:Partial<Record<NotificationStatus,string>>={};
          results.forEach((result,index)=>{
            if(result.status==='fulfilled'){
              nextItems.push(...result.value.items);nextCursors[statuses[index]]=result.value.next_cursor;
              errors[statuses[index]]=result.value.errors.map(e=>e.message).join(' ');
            }else errors[statuses[index]]=result.reason instanceof Error?result.reason.message:'通知读取失败。';
          });
          setNow(Date.now());setItems(orderedNotifications(nextItems));setCursors(nextCursors);setListErrors(errors);setError('');
        }
      }}finally{running=false;if(active)setLoading(false);}
    }
    refreshList.current=()=>void refresh();void refresh();
    return()=>{active=false;generation.current++;controller.abort();refreshList.current=()=>{};};
  },[]);
  useEffect(()=>refreshList.current(),[notifications.revision]);
  async function more(){
    const status=cursors.pending?'pending':'read',cursor=cursors[status];
    if(!cursor||loading)return;const current=generation.current;setLoading(true);
    try{const page=await readNotifications(status,cursor);if(current===generation.current){setItems(old=>orderedNotifications([...old,...page.items]));setCursors(old=>({...old,[status]:page.next_cursor}));setListErrors(old=>({...old,[status]:page.errors.map(e=>e.message).join(' ')}));}}
    catch(cause){if(current===generation.current)setListErrors(old=>({...old,[status]:cause instanceof Error?cause.message:'通知读取失败。'}));}finally{if(current===generation.current)setLoading(false);}
  }
  async function act(item:NotificationItem,action:NotificationAction){setBusy(item.notification_id);try{await actNotification(item.notification_id,action);setItems(old=>orderedNotifications(old.map(value=>value.notification_id===item.notification_id?{...value,status:'read',actions:[]}:value)));notifications.refresh();}catch(cause){setError(cause instanceof Error?cause.message:'通知操作失败。');}finally{setBusy(null);}}
  function target(item:NotificationItem):RoutePath|null{const {member_id,resource_id,resource_type}=item.target;if(!resource_id)return null;if(resource_type==='conversation')return chatPathForSession(resource_id);if(!member_id)return null;if(resource_type==='medication_batch'&&item.target.medication_id)return medicationBatchPath(member_id,item.target.medication_id,resource_id);if(resource_type==='medication_plan')return medicationPath(member_id,'plans',resource_id);return null;}
  return <section className="workspace-panel notification-workspace" aria-label="通知中心">
    <WorkspaceToolbar title="通知" showBack={false} leading={sidebarToggle}/>
    <div className="notification-content">
    {feedback?<div role="alert" className="notification-feedback">{feedback}<button className="control" onClick={notifications.refresh}>重试</button></div>:null}
    <div className="notification-list scroll-content content-column" aria-busy={loading}>
      {items.length ? <GroupedList density="standard">
      {items.map(item=>{const path=target(item);return <article className="notification-card standard-control-bar" data-row-surface key={item.notification_id} data-notification-id={item.notification_id} data-status={item.status}>
        <button className="notification-open" data-interaction-owner="row" type="button" disabled={!path} onClick={()=>{if(path)onNavigate(path);}} aria-label={`${item.title}，查看详情`}>
          <ControlRowContent title={item.title} description={item.message} singleLineDescription />
        </button>
        <div className="notification-meta">
          <time dateTime={item.occurred_at}>{notificationTime(item.occurred_at,now)}</time>
          {item.actions.includes('read')?<button className="control control--inline control--icon control--ghost" data-interaction-owner="self" title="标为已读" aria-label="标为已读" disabled={busy===item.notification_id} onClick={()=>void act(item,'read')}><CheckIcon/></button>:null}
        </div>
      </article>;})}
      </GroupedList> : null}
      {!items.length&&!loading&&!feedback?<EmptyState layout="inline" title="暂无通知"/>:null}
      {loading?<p role="status">正在读取通知…</p>:null}{cursors.pending||cursors.read?<button className="control" disabled={loading} onClick={()=>void more()}>继续加载</button>:null}
    </div>
    </div>
  </section>;
}
