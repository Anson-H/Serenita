import {useState} from 'react';
import {Switch} from '../../components/Switch';
import {GroupedList} from '../../components/GroupedList';
import type {NotificationSwitch} from '../../api/notificationApi';
import {useNotifications} from '../notifications/NotificationProvider';

const notificationTypes: {key:NotificationSwitch;label:string}[] = [
  {key:'medication_due_enabled',label:'用药提醒'},
  {key:'medication_expired_enabled',label:'药品过期提醒'},
  {key:'answer_completed_enabled',label:'回答已生成'},
];

export function NotificationSettings(){
  const notifications=useNotifications();
  const [busy,setBusy]=useState(false),[error,setError]=useState('');
  async function save(key:NotificationSwitch,value:boolean){
    setBusy(true);setError('');
    try{await notifications.savePreferences({[key]:value});}
    catch(cause){setError(cause instanceof Error?cause.message:'通知设置未保存。');}
    finally{setBusy(false);}
  }
  const disabled=!notifications.preferences||busy;
  return <section className="settings-section" aria-label="通知设置">
    <GroupedList layout="fields" density="standard" role="group" aria-label="总通知">
      <label className="field-row"><span className="field-label">总通知</span><Switch label="总通知" checked={notifications.preferences?.notifications_enabled??false} disabled={disabled} onChange={value=>void save('notifications_enabled',value)}/></label>
    </GroupedList>
    <GroupedList layout="fields" density="standard" role="group" aria-label="通知类型">
      {notificationTypes.map(({key,label})=><label className="field-row" key={key}><span className="field-label">{label}</span><Switch label={label} checked={notifications.preferences?.[key]??false} disabled={disabled} onChange={value=>void save(key,value)}/></label>)}
    </GroupedList>
    {error||notifications.error?<p role="alert">{error||notifications.error}</p>:null}
  </section>;
}
