import {useEffect} from 'react';
import {LIST_REFRESH_INTERVAL_MS} from '../../utils/refreshInterval';

export function useMemoryRefresh(read: (signal: AbortSignal) => Promise<void>, enabled = true, refreshOnFocus = false) {
  useEffect(() => {
    if (!enabled) return;
    let controller:AbortController|null=null;
    let pending = false;
    const refresh = () => {
      if (document.visibilityState !== 'visible' || pending) return;
      controller=new AbortController();
      pending = true;
      void read(controller.signal).finally(() => {pending = false;});
    };
    const visibility=()=>{if(document.visibilityState!=='visible')controller?.abort();else if(refreshOnFocus)refresh();};
    const timer = window.setInterval(refresh, LIST_REFRESH_INTERVAL_MS);
    document.addEventListener('visibilitychange',visibility);
    if (refreshOnFocus) window.addEventListener('focus', refresh);
    return () => {window.clearInterval(timer); controller?.abort();
      document.removeEventListener('visibilitychange',visibility);
      if (refreshOnFocus) window.removeEventListener('focus', refresh);};
  }, [read, enabled, refreshOnFocus]);
}
