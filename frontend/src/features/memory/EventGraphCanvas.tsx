import {useId,useLayoutEffect,useMemo,useRef,useState} from 'react';
import {useGraphGestures} from './useGraphGestures';
import type {MemoryGraphRead} from "../../api/memory/memoryGraphApi";
import type {MemoryObject,MemoryReference} from "../../api/memory/memoryApi";
import {objectTitle,object,text,eventRelationLabel} from './memoryPresentation';

type Point={x:number;y:number};
type Node={id:string;reference:MemoryReference;row?:MemoryObject};
function eventCategory(row?:MemoryObject){return text(row?.category)||'事件';}
const excerpt=(value:string,size:number)=>Array.from(value).slice(0,size).join('')+(Array.from(value).length>size?'…':'');
const when=(row?:MemoryObject)=>text(object(object(row?.occurrence_time).start).value)||'';

function arrange(nodes:Node[],edges:MemoryGraphRead['edges']):Record<string,Point>{
 const positions:Record<string,Point>={},speed:Record<string,Point>={};
 const radius=Math.max(130,Math.sqrt(nodes.length)*95);
 nodes.forEach((node,i)=>{const angle=i*2.399963;const r=radius*Math.sqrt((i+.5)/nodes.length);positions[node.id]={x:Math.cos(angle)*r,y:Math.sin(angle)*r};speed[node.id]={x:0,y:0};});
 for(let step=0;step<180;step++){
  const forces:Record<string,Point>={};nodes.forEach(node=>{const p=positions[node.id];forces[node.id]={x:-p.x*.012,y:-p.y*.012};});
  nodes.forEach((a,i)=>nodes.slice(i+1).forEach(b=>{const p=positions[a.id],q=positions[b.id];const dx=p.x-q.x,dy=p.y-q.y,d=Math.max(1,Math.hypot(dx,dy));const f=Math.min(22,23000/(d*d));forces[a.id].x+=dx/d*f;forces[a.id].y+=dy/d*f;forces[b.id].x-=dx/d*f;forces[b.id].y-=dy/d*f;}));
  edges.forEach(edge=>{const a=positions[edge.from.object_id],b=positions[edge.to.object_id];if(!a||!b)return;const dx=b.x-a.x,dy=b.y-a.y,d=Math.max(1,Math.hypot(dx,dy)),f=(d-215)*.018;forces[edge.from.object_id].x+=dx/d*f;forces[edge.from.object_id].y+=dy/d*f;forces[edge.to.object_id].x-=dx/d*f;forces[edge.to.object_id].y-=dy/d*f;});
  nodes.forEach(node=>{const v=speed[node.id],f=forces[node.id],p=positions[node.id];v.x=(v.x+f.x)*.65;v.y=(v.y+f.y)*.65;p.x+=v.x;p.y+=v.y;});
 }
 return positions;
}

export function EventGraphCanvas({value,onRead}:{value:MemoryGraphRead;onRead:(reference:MemoryReference)=>void}){
 const marker=useId().replace(/:/g,'');
 const edges=value.edges.filter(edge=>edge.edge_kind==='event_relation'&&edge.from.object_type==='event'&&edge.to.object_type==='event');
 const refs=[...new Map([...value.nodes.filter(ref=>ref.object_type==='event'),...edges.flatMap(edge=>[edge.from,edge.to])].map(ref=>[ref.object_id,ref])).values()];
 const nodes:Node[]=refs.map(ref=>({id:ref.object_id,reference:ref,row:value.objects.find(row=>row.object_type==='event'&&row.event_id===ref.object_id)}));
 const topology=JSON.stringify([refs.map(ref=>ref.object_id),edges.map(edge=>[edge.from.object_id,edge.to.object_id])]);
 // Layout depends only on actual topology; no inferred relationship is drawn.
 const layout=useMemo(()=>arrange(nodes,edges),[topology]); // eslint-disable-line react-hooks/exhaustive-deps
 const [overrides,setOverrides]=useState<Record<string,Point>>({});
 const positions={...layout,...overrides};
 const frame=useRef<HTMLDivElement>(null),svg=useRef<SVGSVGElement>(null);
 const [viewport,setViewport]=useState({width:0,height:0});
 useLayoutEffect(()=>{
  const element=frame.current;
  if(!element)return;
  const measure=()=>setViewport({width:element.clientWidth,height:element.clientHeight});
  measure();
  const observer=new ResizeObserver(measure);
  observer.observe(element);
  return()=>observer.disconnect();
 },[]);
 const bounds=Object.values(layout);
 const minX=Math.min(...bounds.map(p=>p.x),0),maxX=Math.max(...bounds.map(p=>p.x),0);
 const minY=Math.min(...bounds.map(p=>p.y),0),maxY=Math.max(...bounds.map(p=>p.y),0);
 // Fit large graphs while keeping sparse graphs at their natural size initially.
 const width=Math.max(500,maxX-minX+290,viewport.width);
 const height=Math.max(350,maxY-minY+230,viewport.height);
 const fit={x:(minX+maxX-width)/2,y:(minY+maxY+30-height)/2,width,height};
 const [camera,setCamera]=useState<typeof fit|null>(null);const view=camera||fit;
 const [hover,setHover]=useState<{node:Node;x:number;y:number}|null>(null);
 const gestures=useGraphGestures({svg,view,fit,positions,onView:setCamera,onInteract:()=>setHover(null),
  onNodeMove:(id,point)=>setOverrides(current=>({...current,[id]:point})),
  onTap:target=>{const id=target.closest('[data-event-id]')?.getAttribute('data-event-id');
   if(id){const node=nodes.find(node=>node.id===id);if(node)onRead(node.reference);return;}
   const relation=target.closest('[data-relation]')?.getAttribute('data-relation');
   if(relation!=null&&edges[Number(relation)]){const edge=edges[Number(relation)];if(edge.relation||edge.basis)onRead((edge.relation||edge.basis)!);};
  }});
 function preview(node:Node,element:SVGGElement){if(gestures.isInteracting())return;const b=element.getBoundingClientRect(),f=frame.current?.getBoundingClientRect();if(f)setHover({node,x:Math.max(12,Math.min(f.width-292,b.x-f.x+b.width/2-140)),y:Math.max(12,Math.min(f.height-190,b.bottom-f.top+12))});}
 const related=new Set(hover?[hover.node.id,...edges.filter(edge=>edge.from.object_id===hover.node.id||edge.to.object_id===hover.node.id).flatMap(edge=>[edge.from.object_id,edge.to.object_id])]:[]);
 return <div className="event-graph-frame" ref={frame}>
  <svg ref={svg} className="event-graph-canvas" role="group" aria-label="事件关系图" viewBox={`${view.x} ${view.y} ${view.width} ${view.height}`}
   {...gestures.handlers} onPointerLeave={()=>{if(!gestures.isInteracting())setHover(null);}}>
   <defs><marker id={`${marker}-arrow`} viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 10 z" fill="context-stroke"/></marker></defs>
   {edges.map((edge,index)=>{const a=positions[edge.from.object_id],b=positions[edge.to.object_id];if(!a||!b)return null;
    const dx=b.x-a.x,dy=b.y-a.y,d=Math.max(1,Math.hypot(dx,dy));const start={x:a.x+dx/d*44,y:a.y+dy/d*44},end={x:b.x-dx/d*49,y:b.y-dy/d*49};
    const parallel=edges.filter(item=>[item.from.object_id,item.to.object_id].sort().join('|')===[edge.from.object_id,edge.to.object_id].sort().join('|'));
    const offset=(parallel.indexOf(edge)-(parallel.length-1)/2)*72*(edge.from.object_id<edge.to.object_id?1:-1);const mid={x:(a.x+b.x)/2-dy/d*offset,y:(a.y+b.y)/2+dx/d*offset};
    const path=edge.from.object_id===edge.to.object_id?`M ${a.x-30} ${a.y-30} C ${a.x-125} ${a.y-155},${a.x+125} ${a.y-155},${a.x+30} ${a.y-30}`:`M ${start.x} ${start.y} Q ${mid.x} ${mid.y} ${end.x} ${end.y}`;
    const labelPoint={x:(start.x+2*mid.x+end.x)/4,y:(start.y+2*mid.y+end.y)/4};
    const label=edge.edge_kind==='event_relation'?eventRelationLabel(edge.relation_type):'关联';const highlighted=!hover||edge.from.object_id===hover.node.id||edge.to.object_id===hover.node.id;
    return <g className={`event-graph-edge${highlighted?'':' is-dimmed'}`} key={`${edge.relation?.object_id||index}`}>
     <path className="event-graph-link" d={path} markerEnd={`url(#${marker}-arrow)`} markerStart={edge.direction==='symmetric'?`url(#${marker}-arrow)`:undefined}/>
     <g data-relation={index} role="button" tabIndex={0} aria-label={`查看${label}关系`} className="event-graph-edge-label" transform={`translate(${edge.from.object_id===edge.to.object_id?a.x:labelPoint.x} ${edge.from.object_id===edge.to.object_id?a.y-110:labelPoint.y})`}
      onKeyDown={event=>{if((event.key==='Enter'||event.key===' ')&&(edge.relation||edge.basis)){event.preventDefault();onRead((edge.relation||edge.basis)!);}}}>
      <rect x={-(label.length*12+32)/2} y="-12" width={label.length*12+32} height="24" rx="12"/><text textAnchor="middle" y="4">{label}{edge.direction==='symmetric'?' ↔':' →'}</text></g>
    </g>;})}
   {nodes.map(node=>{const p=positions[node.id],title=node.row?objectTitle(node.row):'尚未展开的事件';const type=eventCategory(node.row),letters=Array.from(type),lines=letters.length>4?[letters.slice(0,4).join(''),excerpt(letters.slice(4).join(''),4)]:[type];return <g key={node.id} data-event-id={node.id} role="button" tabIndex={0}
     aria-label={`查看事件：${title}`} className={`event-graph-event${node.row?'':' is-boundary'}${hover&&!related.has(node.id)?' is-dimmed':''}`} transform={`translate(${p.x} ${p.y})`}
     onPointerEnter={event=>preview(node,event.currentTarget)} onPointerLeave={()=>setHover(null)} onFocus={event=>preview(node,event.currentTarget)} onBlur={()=>setHover(null)}
     onKeyDown={event=>{if(event.key==='Enter'||event.key===' '){event.preventDefault();setHover(null);onRead(node.reference);}}}>
      <circle className="event-graph-halo" r="49"/><circle className="event-graph-dot" r="40"/><text className="event-graph-type" textAnchor="middle">{lines.map((line,index)=><tspan key={index} x="0" y={lines.length===1?4:index===0?-5:13}>{line}</tspan>)}</text>
      <text className="event-graph-title" textAnchor="middle" y="68">{excerpt(title,15)}</text>{when(node.row)?<text className="event-graph-date" textAnchor="middle" y="87">{when(node.row).slice(0,10)}</text>:null}
    </g>;})}
  </svg>
  {!nodes.length?<p className="memory-empty event-graph-empty" role="status">当前范围没有可显示的事件。</p>:null}
  {hover?<div className="event-graph-tooltip" role="tooltip" style={{left:hover.x,top:hover.y}}><strong>{hover.node.row?eventCategory(hover.node.row):'未展开的事件'}</strong>
   <p>{hover.node.row?objectTitle(hover.node.row):'此事件尚未加载详情。'}</p>{when(hover.node.row)?<span>{when(hover.node.row)}</span>:null}</div>:null}
 </div>;
}
