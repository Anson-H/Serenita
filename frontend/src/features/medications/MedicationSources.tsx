import {OriginalFileThumbnail} from "../../components/OriginalFileThumbnail";
import {useEffect,useRef,useState} from 'react';
import {FilePreview} from '../../components/FilePreview';
import type {MedicationSource,MedicationItem} from '../../api/medicationTypes';
import {addMedicationSources,medicationSourceUrl,readMedicationSource} from '../../api/medicationApi';
import {UploadIcon} from '../../components/icons';

export function MedicationSources({member,item,canEdit,onReload}:{member:string;item:MedicationItem|null;canEdit:boolean;onReload:()=>void}) {
  const [uploads,setUploads]=useState<{files:File[];request:string}|null>(null);
  const [busy,setBusy]=useState(false);const [error,setError]=useState('');
  const [selected,setSelected]=useState<MedicationSource|null>(null);
  const [preview,setPreview]=useState<{url:string;text:string}|null>(null);const [previewError,setPreviewError]=useState('');
  const input=useRef<HTMLInputElement>(null);const active=useRef(true);const editable=useRef(canEdit);editable.current=canEdit;
  const id=String(item?.medication_id??'');const files=item?.sources??[];
  const primary=files.find(f=>f.is_primary)??files[0];
  useEffect(()=>{active.current=true;return()=>{active.current=false;};},[]);
  useEffect(()=>{if(selected&&!files.some(f=>f.resource_id===selected.resource_id))setSelected(null);},[item]);
  useEffect(()=>{
    setPreview(null);setPreviewError('');if(!selected)return;
    const controller=new AbortController();let url:string|undefined;
    void readMedicationSource(member,id,selected.resource_id,controller.signal).then(async blob=>{
      const text=selected.mime_type.startsWith('text/')?await blob.text():'';
      if(controller.signal.aborted)return;url=URL.createObjectURL(blob);setPreview({url,text});
    }).catch(e=>{if(!controller.signal.aborted)setPreviewError(e.message||'文件读取失败');});
    return()=>{controller.abort();if(url)URL.revokeObjectURL(url);};
  },[member,id,selected]);
  async function sendFiles(queue:NonNullable<typeof uploads>){
    if(!item||!editable.current)return;setUploads(queue);setBusy(true);setError('');
    try{
      await addMedicationSources(id,queue.files,queue.request);
      if(active.current){setUploads(null);onReload();}
    }catch(e){if(active.current)setError(e instanceof Error?e.message:'原件上传失败');}finally{if(active.current)setBusy(false);}
  }
  return <>
    <section className="report-overview-thumbnail medication-overview-files" aria-label="药品图片与文件">
      <OriginalFileThumbnail fileId={primary?.resource_id} previewUrl={primary?.mime_type.startsWith('image/')?medicationSourceUrl(member,id,primary.resource_id):undefined} text={primary?.mime_type.startsWith('text/')} count={files.length} onOpen={()=>{if(primary)setSelected(primary);}}/>
      {canEdit?<><button className="control control--secondary report-source-add-button" type="button" disabled={!item||busy||!!uploads} onClick={()=>input.current?.click()}><UploadIcon/><span>{busy?'正在补充':'补充原件'}</span></button><input ref={input} hidden type="file" multiple accept="image/jpeg,image/png,image/heic,application/pdf,text/plain" onChange={e=>{const selectedFiles=Array.from(e.target.files??[]);e.currentTarget.value='';if(selectedFiles.length)void sendFiles({files:selectedFiles,request:crypto.randomUUID()});}}/></>:null}
      {uploads&&!busy?<div className="medication-actions"><button className="control control--compact" type="button" onClick={()=>void sendFiles(uploads)}>重试上传（{uploads.files.length}）</button><button className="control control--compact" type="button" onClick={()=>setUploads(null)}>取消上传</button></div>:null}
      {error?<p role="alert">{error}</p>:null}
    </section>
    {selected?<FilePreview file={{id:selected.resource_id,name:selected.original_filename,mimeType:selected.mime_type}} files={files.map(file=>({id:file.resource_id,name:file.original_filename,mimeType:file.mime_type}))} objectUrl={preview?.url} textContent={preview?.text} loading={!preview&&!previewError} error={previewError||error} onRetry={previewError?()=>setSelected({...selected}):undefined} onSelect={file=>setSelected(files.find(f=>f.resource_id===file.id)??null)} onClose={()=>setSelected(null)}/>:null}
  </>;
}
