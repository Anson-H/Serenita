import type { ReactNode } from 'react';

/** Reuse the existing controls' footprint so selection never pushes the list down. */
export function ListSelectionSlot({active,selection,children,onCancel}:{active:boolean;selection:ReactNode;children:ReactNode;onCancel?:()=>void}) {
  return <div className="list-selection-slot" data-selecting={active?"true":undefined} onKeyDown={event=>{
    if(active&&onCancel&&event.key==='Escape'){event.preventDefault();event.stopPropagation();onCancel();}
  }}>
    <div className="list-selection-slot-source" inert={active} aria-hidden={active?true:undefined}>{children}</div>
    {active?<div className="list-selection-slot-active">{selection}</div>:null}
  </div>;
}
