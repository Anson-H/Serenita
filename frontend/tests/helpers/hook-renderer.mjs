// Minimal effect/state scheduler for testing our persistence hooks without a DOM.
export function hookRenderer() {
  const slots=[];let cursor=0,changed=false,effects=[],callback,value;
  const same=(a,b)=>a&&b&&a.length===b.length&&a.every((entry,i)=>Object.is(entry,b[i]));
  const react={
    useRef(initial){const i=cursor++;return slots[i]??= {current:initial};},
    useMemo(make,deps){const i=cursor++;if(!slots[i]||!same(slots[i].deps,deps))slots[i]={deps,value:make()};return slots[i].value;},
    useState(initial){const i=cursor++;if(!slots[i])slots[i]={value:typeof initial==='function'?initial():initial};return [slots[i].value,next=>{const value=typeof next==='function'?next(slots[i].value):next;if(!Object.is(value,slots[i].value)){slots[i].value=value;changed=true;}}];},
    useEffect(setup,deps){const i=cursor++;if(!slots[i]||!same(slots[i].deps,deps)){const previous=slots[i];slots[i]={deps,cleanup:previous?.cleanup};effects.push(()=>{previous?.cleanup?.();slots[i].cleanup=setup();});}},
    useSyncExternalStore(subscribe,snapshot){react.useEffect(()=>subscribe(()=>{changed=true;}),[subscribe]);return snapshot();}
  };
  function render(next=callback){callback=next;let loops=0;do{if(++loops>30)throw Error('hook render loop');changed=false;cursor=0;effects=[];value=callback();for(const effect of effects)effect();}while(changed);return value;}
  return {react,render,get value(){return value;},unmount(){for(const slot of slots)slot?.cleanup?.();}};
}
