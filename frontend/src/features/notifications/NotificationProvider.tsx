import {createContext,useContext,useEffect,useRef,useState,type ReactNode} from 'react';
import {openNotificationEvents,readNotificationPreferences,readNotificationSummary,saveNotificationPreferences,type NotificationPreferences,type NotificationPreferenceChanges} from '../../api/notificationApi';
import {publishAuthInvalidation} from '../../api/authSessionEvents';
type State = {preferences:NotificationPreferences|null;count:number|null;revision:number;error:string;refresh:()=>void;savePreferences:(changes:NotificationPreferenceChanges)=>Promise<void>};
const Context = createContext<State|null>(null);
export function NotificationProvider({children}:{children:ReactNode}){
  const [preferences,setPreferences]=useState<NotificationPreferences|null>(null);
  const [count,setCount]=useState<number|null>(null),[revision,setRevision]=useState(0);
  const [error,setError]=useState('');
  const refreshRef=useRef<()=>void>(()=>{}),settingsGeneration=useRef(0);
  useEffect(()=>{
    let active=true,running=false,dirty=false;
    let timer:ReturnType<typeof setTimeout>|undefined;
    const controller=new AbortController(),events=openNotificationEvents();
    async function flush(){
      if(!active)return;dirty=true;if(running)return;running=true;
      try{while(active&&dirty){
        dirty=false;setRevision(v=>v+1);const generation=settingsGeneration.current;
        try{const [pref,summary]=await Promise.all([readNotificationPreferences(controller.signal),readNotificationSummary(controller.signal)]);
          if(active){if(generation===settingsGeneration.current)setPreferences(pref);setCount(summary.pending_count);setError(summary.errors.map(e=>e.message).join(' '));}
        }catch(cause){if(active){setCount(null);setError(cause instanceof Error?cause.message:'通知读取失败。');}}
      }}finally{running=false;}
    }
    function refresh(){if(running){dirty=true;return;}if(timer)return;timer=setTimeout(()=>{timer=undefined;void flush();},100);}
    function onExpired(){active=false;controller.abort();events.close();setPreferences(null);setCount(null);publishAuthInvalidation(401);}
    function onVisibility(){if(document.visibilityState==='visible')refresh();}
    refreshRef.current=refresh;
    // EventSource reconnects automatically; reconnection stays silent in the UI.
    events.addEventListener('open',refresh);events.addEventListener('notifications_changed',refresh);events.addEventListener('authentication_expired',onExpired);
    window.addEventListener('focus',refresh);window.addEventListener('serenita:member-access-changed',refresh);document.addEventListener('visibilitychange',onVisibility);
    void flush();
    return()=>{active=false;controller.abort();clearTimeout(timer);events.close();refreshRef.current=()=>{};window.removeEventListener('focus',refresh);window.removeEventListener('serenita:member-access-changed',refresh);document.removeEventListener('visibilitychange',onVisibility);};
  },[]);
  async function savePreferences(changes:NotificationPreferenceChanges){settingsGeneration.current++;const pref=await saveNotificationPreferences(changes);settingsGeneration.current++;setPreferences(pref);refreshRef.current();}
  return <Context.Provider value={{preferences,count,revision,error,refresh:()=>refreshRef.current(),savePreferences}}>{children}</Context.Provider>;
}
export function useNotifications(){const value=useContext(Context);if(!value)throw new Error('通知服务未装配');return value;}
