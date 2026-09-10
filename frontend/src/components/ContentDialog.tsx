import {useId,useRef,type ReactNode} from 'react';
import {createPortal} from 'react-dom';
import {DialogTitlebar} from './DialogTitlebar';
import {useModalDialog} from './useModalDialog';

export function ContentDialog({title,onClose,onBack,creation=false,busy=false,children,actions,bodyClassName='',bareBody=false}:{title:string;onClose:()=>void;onBack?:()=>void;creation?:boolean;busy?:boolean;children:ReactNode;actions?:ReactNode;bodyClassName?:string;bareBody?:boolean}) {
  const ref=useRef<HTMLElement>(null);
  const id=useId();
  useModalDialog({active:true,dialogRef:ref,onEscape:onClose,escapeDisabled:busy});
  return createPortal(<div className="content-dialog-backdrop dialog-viewport-backdrop" onMouseDown={event=>{if(event.target===event.currentTarget&&!busy)onClose();}}>
    <section onSubmit={event=>event.stopPropagation()} ref={ref} role="dialog" aria-modal="true" aria-labelledby={id} tabIndex={-1} className={`content-dialog dialog-viewport-surface dialog-title-ellipsis${creation?' creation-dialog':''}`}>
      <DialogTitlebar id={id} title={title} onClose={onClose} onBack={onBack} busy={busy}/>
      {bareBody?children:<div className={`dialog-body scroll-content ${bodyClassName}`}>{children}</div>}
      {actions?<footer className="dialog-action-bar">{actions}</footer>:null}
    </section>
  </div>,document.body);
}
