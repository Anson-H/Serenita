import { EmptyState } from "./EmptyState";
import {useId,useLayoutEffect,useRef} from 'react';
import {createPortal} from 'react-dom';
import {GroupedList} from './GroupedList';
import {AudioFormatIcon,DocumentFormatIcon,DownloadIcon,ImageFormatIcon,OtherFormatIcon,TextFormatIcon,TrashIcon,VideoFormatIcon,XIcon} from './icons';
import {useModalDialog} from './useModalDialog';

export type PreviewFile={id:string;name:string;mimeType:string;thumbnailUrl?:string|null;isPrimary?:boolean};
function FileIcon({mimeType}:{mimeType:string}) {
  const Icon=mimeType.startsWith('text/')?TextFormatIcon:mimeType.startsWith('image/')?ImageFormatIcon:mimeType.startsWith('audio/')?AudioFormatIcon:mimeType.startsWith('video/')?VideoFormatIcon:mimeType==='application/pdf'?DocumentFormatIcon:OtherFormatIcon;
  return <Icon className="file-preview-file-icon"/>;
}
export function FilePreview({file,files,objectUrl,textContent,loading=false,error='',imageLabel,onSelect,onClose,onRetry,onDelete,deleting=false}:{
  file:PreviewFile;files:PreviewFile[];objectUrl?:string;textContent?:string;loading?:boolean;error?:string;imageLabel?:string;
  onSelect:(file:PreviewFile)=>void;onClose:()=>void;onRetry?:()=>void;onDelete?:()=>void;deleting?:boolean;
}) {
  const dialogRef=useRef<HTMLElement>(null);const headingRef=useRef<HTMLHeadingElement>(null);const headingId=useId();
  const actionsRef=useRef<HTMLDivElement>(null);
  useLayoutEffect(()=>{
    const actions=actionsRef.current;
    if(!actions)return;
    const measure=()=>dialogRef.current?.style.setProperty('--file-preview-actions-width',`${actions.getBoundingClientRect().width}px`);
    measure();
    const observer=new ResizeObserver(measure);
    observer.observe(actions);
    return ()=>observer.disconnect();
  },[]);
  useModalDialog({active:true,dialogRef,initialFocusRef:headingRef,onEscape:onClose});
  const kind=file.mimeType.startsWith('image/')?'image':file.mimeType==='application/pdf'?'pdf':file.mimeType.startsWith('text/')?'text':'unsupported';
  return createPortal(<div className="file-preview-backdrop dialog-viewport-backdrop" onMouseDown={event=>{if(event.currentTarget===event.target)onClose();}}>
    <section aria-labelledby={headingId} aria-modal="true" className="file-preview dialog-viewport-surface" ref={dialogRef} role="dialog" tabIndex={-1}>
      <header className="dialog-titlebar">
        <h3 className="file-preview-heading file-preview-focus-target" id={headingId} title={file.name} ref={headingRef} tabIndex={-1}>{file.name}</h3>
        <div className="file-preview-actions" ref={actionsRef}>
          {onDelete?<button type="button" aria-label={`删除原件 ${file.name}`} className="control control--titlebar control--icon control--ghost control--danger titlebar-icon-control" disabled={deleting} onClick={onDelete}><TrashIcon/></button>:null}
          {objectUrl?<a aria-label="下载" title="下载" className="control control--titlebar control--icon control--ghost file-preview-titlebar-action file-preview-download titlebar-icon-control" download={file.name} href={objectUrl}><DownloadIcon className="file-preview-titlebar-action-icon"/></a>:null}
          <button aria-label="关闭原件预览" className="control control--titlebar control--icon control--ghost file-preview-titlebar-action file-preview-close titlebar-icon-control" onClick={onClose} type="button"><XIcon/></button>
        </div>
      </header>
      <div className="dialog-body file-preview-body" data-single-source={files.length>1?undefined:'true'}>
        {files.length>1?<aside aria-label={`关联文件，共 ${files.length} 个`} className="file-preview-files scroll-content">
          <header><strong>关联文件</strong><span>{files.length} 个</span></header>
          <GroupedList as="ul" className="file-preview-file-list" density="standard">{files.map(entry=><li key={entry.id}>
            <button aria-current={entry.id===file.id?'page':undefined} aria-label={`查看${entry.isPrimary?'主文件':'关联文件'}：${entry.name}`} data-interaction-owner="row" disabled={loading||deleting} onClick={()=>{if(entry.id!==file.id)onSelect(entry);}} type="button">
              <FileIcon mimeType={entry.mimeType}/><span className="file-preview-file-name">{entry.name}</span>{entry.isPrimary?<span className="file-preview-file-status">主文件</span>:null}
            </button>
          </li>)}</GroupedList>
        </aside>:null}
        <div aria-busy={loading?'true':undefined} className="file-preview-frame" data-preview-kind={kind}>
          {error?<div role="alert"><p>{error}</p>{onRetry?<button className="control" type="button" onClick={onRetry}>重试</button>:null}</div>:null}
          {objectUrl&&!error?<>
            {kind==='image'?<img alt={imageLabel??file.name} src={objectUrl}/>:null}
            {kind==='pdf'?file.thumbnailUrl?<img alt={`${imageLabel??file.name} PDF 第一页`} src={file.thumbnailUrl}/>:<iframe src={`${objectUrl}#page=1&view=Fit`} title={`${imageLabel??file.name} PDF 第一页预览`}/>:null}
            {kind==='text'?<pre className="file-preview-text scroll-content">{textContent??''}</pre>:null}
            {kind==='unsupported'?<EmptyState layout="inline" title="浏览器无法直接预览此文件" description="可下载后使用本地应用打开。" />:null}
          </>:loading?<p role="status">正在读取文件…</p>:null}
        </div>
      </div>
    </section>
  </div>,document.body);
}
