import { navigationLabels } from "../../components/navigationLabels";
import {useRef,useState} from 'react';
import type {DoseTime} from '../../api/medicationTypes';
import {DateTimePicker} from '../../components/DateTimePicker';
import {PlusIcon} from '../../components/icons';
import {GroupedList} from '../../components/GroupedList';
import {useListDeleteActions} from '../../components/useListDeleteActions';
import {focusWithoutScroll} from '../../utils/inputMethod';
import {localDateTimeInputValue} from '../../utils/localTime';

export function MedicationTimeFields({times,disabled,onChange}:{times:DoseTime[];disabled:boolean;onChange:(times:DoseTime[])=>void}) {
  const [picker,setPicker]=useState<{index:number;value:string}|null>(null);
  const [error,setError]=useState('');
  const content=useRef<HTMLDivElement>(null);
  const actions=useListDeleteActions({scope:'medication-times',enabled:!disabled,label:'用药时间',countLabel:'个时间',entries:times.map(time=>({id:time.time,name:time.time})),onDelete:async ids=>{
    setPicker(null);setError('');onChange(times.filter(time=>!ids.includes(time.time)));return [];
  }});
  function open(index:number){setError('');setPicker({index,value:times[index]?.time??localDateTimeInputValue(new Date()).slice(11,16)});}
  function close(label:string,restore:boolean){setPicker(null);setError('');if(restore)requestAnimationFrame(()=>focusWithoutScroll(content.current?.querySelector<HTMLElement>(`button[aria-label="${label}"]`)??null));}
  function input(index:number){return picker?.index===index?<DateTimePicker ariaLabel={index===times.length?navigationLabels.addTime:`时间 ${index+1}`} disabled={disabled} presentation={index===times.length?"create-dialog":"popover"} mode="time" value={picker.value} validationMessage={error}
    onChange={value=>{setError('');setPicker({index,value});}}
    onCancel={()=>close(index===times.length?navigationLabels.addTime:`时间 ${index+1}`,true)}
    onCommit={(value,reason)=>{
      if(times.some((time,i)=>i!==index&&time.time===value)){setError('此时间已添加，请选择其他时间。');return;}
      onChange(index===times.length?[...times,{time:value}]:times.map((time,i)=>i===index?{time:value}:time));
      close(`时间 ${index+1}`,reason==='done');
    }}/>:null;}
  return <div ref={content} onKeyDown={actions.onKeyDown}><section><div className="group-heading"><h2>固定时间</h2></div>{actions.heading}<GroupedList layout="fields" density="standard" selectionMode={actions.selectionMode?'multiple':undefined}>
    {!disabled&&!actions.selectionMode?<div className="medication-time-add-row"><button className="control control--row grouped-list-create-button" data-interaction-owner="row" aria-label={navigationLabels.addTime} type="button" disabled={actions.busy} onClick={()=>open(times.length)}><PlusIcon/>{navigationLabels.addTime}</button>{picker?.index===times.length?input(times.length):null}</div>:null}
    {times.map((time,index)=>actions.selectionMode?<button {...actions.rowProps(time.time)} className="control control--row medication-time-choice" key={time.time} type="button" role="checkbox" aria-label={`时间 ${index+1}：${time.time}`} aria-checked={actions.selected(time.time)} disabled={actions.busy} onClick={()=>actions.toggle(time.time)}>{actions.indicator(time.time)}<span>时间 {index+1}</span><span>{time.time}</span></button>:<div {...actions.rowProps<HTMLDivElement>(time.time,'.report-inline-edit-trigger')} className="field-row" key={time.time}><span className="field-label">时间 {index+1}</span><div className="field-value medication-time-controls">
      {disabled?<span>{time.time}</span>:<>{picker?.index===index?input(index):<button className="report-inline-edit-trigger" data-interaction-owner="row" type="button" aria-label={`时间 ${index+1}`} aria-haspopup="dialog" aria-expanded="false" onClick={()=>open(index)}>{time.time}</button>}
      </>}
    </div></div>)}
    {disabled&&!times.length?<div className="field-row">未记录固定时间</div>:null}
  </GroupedList>{actions.toolbar}{actions.portal}</section></div>;
}
