import type {MemoryProcessingStep} from "../../api/memory/memoryApi";
import {objects,text} from './memoryPresentation';

const owns=(value:Record<string,unknown>,key:string)=>Object.prototype.hasOwnProperty.call(value,key);
function Value({value,present}:{value:unknown;present:boolean}){
  return present?<div className="text-input-surface memory-change-markdown"><pre className="memory-model-code">{JSON.stringify(value,null,2)}</pre></div>:<p className="memory-metadata">未记录。</p>;
}

export function MemoryStepIO({steps,title,leaf=true}:{steps:MemoryProcessingStep[];title:string;leaf?:boolean}){
  return <section className="memory-processing-detail" aria-label="处理输入与输出">
    {!steps.length?<p className="memory-metadata">未记录此次处理的输入、输出。</p>:steps.slice(-1).map(step=>{
      const details=step.details;
      const unavailable=text(details.unavailable_reason);
      const operations=objects(details.operations);
      const shown=operations.length?operations:leaf?[{name:title,...details}]:[];
      if(!shown.length&&!unavailable&&!step.error_code&&!step.error_message&&!details.validation_errors)return null;
      return <section className="memory-processing-detail" key={step.progress_id}>
        {unavailable?<p className="memory-metadata">{unavailable}</p>:<>
          {shown.map((operation,index)=><section className="memory-processing-detail" key={index} aria-label="操作输入与输出">
            <h3>第 {index+1} 项操作{text(operation.name)?` · ${text(operation.name)}`:''}</h3>
            <section aria-label="操作输入"><h4>操作输入</h4><Value value={operation.input} present={owns(operation,'input')}/></section>
            <section aria-label="操作输出"><h4>操作输出</h4><Value value={operation.output} present={owns(operation,'output')}/></section>
            {owns(operation,'error')?<Value value={operation.error} present/>:null}
          </section>)}
          {details.validation_errors?<section aria-label="校验错误"><h3>校验错误</h3><Value value={details.validation_errors} present/></section>:null}
        </>}
        {step.error_code||step.error_message?<section aria-label="步骤失败"><h3>步骤失败</h3><Value value={{error_code:step.error_code,error_message:step.error_message}} present/></section>:null}
      </section>;
    })}
  </section>;
}
