import {useEffect,useState} from 'react';
import {DocumentFormatIcon} from './icons';

export function OriginalFileThumbnail({fileId,previewUrl,text=false,loading=false,failed=false,count,onOpen,disabled=false}:{
  fileId?:string;previewUrl?:string;text?:boolean;loading?:boolean;failed?:boolean;count:number;onOpen:()=>void;disabled?:boolean;
}) {
  const [imageFailed,setImageFailed]=useState(false);
  useEffect(()=>setImageFailed(false),[previewUrl]);
  if(!fileId)return <div className="original-file-thumbnail empty"><DocumentFormatIcon className="original-file-thumbnail-icon"/><small>暂无原件</small></div>;
  return <div className="original-file-thumbnail">
    <div className="original-file-thumbnail-frame" aria-hidden="true">
      {previewUrl&&!imageFailed?<img alt="" src={previewUrl} onError={()=>setImageFailed(true)}/>:<div className="original-file-thumbnail-placeholder">{text?<span>TXT</span>:<DocumentFormatIcon className="original-file-thumbnail-icon"/>}<small>{loading&&!failed?'正在载入原件':text?'文本原件':'原件'}</small></div>}
    </div>
    <button className="original-file-thumbnail-open" data-hover="none" data-source-resource-id={fileId} type="button" disabled={disabled} aria-busy={disabled?true:undefined} aria-label={`打开原件预览，共 ${count} 个关联文件`} onClick={onOpen}/>
  </div>;
}
