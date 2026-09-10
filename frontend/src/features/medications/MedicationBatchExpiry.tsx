import {useEffect,useState} from 'react';
import {localDateTimeInputValue} from '../../utils/localTime';

export function MedicationBatchExpiry({expiresOn,separated=false}:{expiresOn:string|null;separated?:boolean}) {
 const [today,setToday]=useState(()=>localDateTimeInputValue(new Date()).slice(0,10));
 useEffect(()=>{
  if(!expiresOn)return;
  let timer:ReturnType<typeof setTimeout>;
  function refresh(){
   clearTimeout(timer);
   const now=new Date();
   setToday(localDateTimeInputValue(now).slice(0,10));
   const tomorrow=new Date(now.getFullYear(),now.getMonth(),now.getDate()+1);
   timer=setTimeout(refresh,tomorrow.getTime()-now.getTime());
  }
  function onVisibility(){if(document.visibilityState==='visible')refresh();}
  refresh();
  window.addEventListener('focus',refresh);
  document.addEventListener('visibilitychange',onVisibility);
  return ()=>{clearTimeout(timer);window.removeEventListener('focus',refresh);document.removeEventListener('visibilitychange',onVisibility);};
 },[expiresOn]);
 return expiresOn&&expiresOn<today?<>{separated?' · ':null}<span className="medication-batch-expiry">已过期</span></>:null;
}
