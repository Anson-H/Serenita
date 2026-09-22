import { useEffect, useRef, useState, type ReactNode } from "react";
import {
  deleteKnowledgeFile, readKnowledgeCatalog, readKnowledgeFile, searchKnowledge, uploadKnowledge,
  type KnowledgeDocument, type KnowledgeMatch, type KnowledgeReading
} from "../../api/knowledge/knowledgeApi";
import { apiUrl } from "../../api/transport/request";
import { ContentDialog } from "../../components/ContentDialog";
import { ControlRowContent } from "../../components/ControlRowContent";
import { EmptyState } from "../../components/EmptyState";
import { GroupedList } from "../../components/GroupedList";
import { TrashIcon, UploadIcon } from "../../components/icons";
import { ListCount } from "../../components/ListCount";
import { WorkspaceToolbar } from "../../components/WorkspaceToolbar";
import "../../styles/knowledge.css";

function errorMessage(error: unknown) {
  return error instanceof Error ? error.message : "操作失败，请重试。";
}

function fileSize(bytes: number) {
  return bytes >= 1024 * 1024 ? `${(bytes / 1024 / 1024).toFixed(1)} MB` : `${Math.max(1, Math.round(bytes / 1024))} KB`;
}

export function KnowledgeFiles({ sidebarToggle, onBack }: { sidebarToggle: ReactNode; onBack: () => void }) {
  const [documents, setDocuments] = useState<(KnowledgeDocument | KnowledgeMatch)[]>([]);
  const [query, setQuery] = useState("");
  const [search, setSearch] = useState("");
  const [revision, setRevision] = useState(0);
  const [cursor, setCursor] = useState<string | null>(null);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [uploadErrors, setUploadErrors] = useState<string[]>([]);
  const [uploadStatus, setUploadStatus] = useState("");
  const [uploading, setUploading] = useState(false);
  const [deleting, setDeleting] = useState<string | null>(null);
  const [selected, setSelected] = useState<{ id: string; name: string; segment: number } | null>(null);
  const input = useRef<HTMLInputElement>(null);
  const workspace = useRef<HTMLElement>(null);
  const uploadActions = useRef<HTMLDivElement>(null);
  const generation = useRef(0);
  const mounted = useRef(true);
  const uploadLock = useRef(false);
  const loadMoreLock = useRef(false);

  useEffect(() => {
    const actions = uploadActions.current;
    if (!actions) return;
    const measure = () => workspace.current?.style.setProperty("--knowledge-action-height", `${actions.getBoundingClientRect().height}px`);
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(actions);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    mounted.current = true;
    return () => { mounted.current = false; generation.current++; };
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    const current = ++generation.current;
    setLoading(true); setError(""); setCursor(null); setDocuments([]);
    async function load() {
      try {
        if (search) {
          const result = await searchKnowledge(search, controller.signal);
          if (current === generation.current) { setDocuments(result.results); setTotal(result.matching_documents); }
        } else {
          const result = await readKnowledgeCatalog(null, controller.signal);
          if (current === generation.current) { setDocuments(result.documents); setTotal(result.total); setCursor(result.next_cursor); }
        }
      } catch (cause) {
        if (!controller.signal.aborted && current === generation.current) setError(errorMessage(cause));
      } finally {
        if (current === generation.current) setLoading(false);
      }
    }
    void load();
    return () => { controller.abort(); generation.current++; };
  }, [search, revision]);

  async function more() {
    if (!cursor || loading || loadMoreLock.current) return;
    loadMoreLock.current = true;
    const current = generation.current;
    setLoading(true); setError("");
    try {
      const result = await readKnowledgeCatalog(cursor);
      if (current === generation.current) {
        setDocuments(previous => [...previous, ...result.documents]); setCursor(result.next_cursor); setTotal(result.total);
      }
    } catch (cause) { if (current === generation.current) setError(errorMessage(cause)); }
    finally { loadMoreLock.current = false; if (current === generation.current) setLoading(false); }
  }

  async function upload(files: File[]) {
    if (!files.length || uploadLock.current) return;
    uploadLock.current = true; setUploading(true); setUploadErrors([]);
    const failures: string[] = [];
    let completed = 0;
    try {
      for (const file of files) {
        if (!mounted.current) break;
        setUploadStatus(`正在处理 ${file.name}（${completed + failures.length + 1}/${files.length}）`);
        try {
          if (!/\.(pdf|docx|md|txt)$/i.test(file.name)) throw new Error("支持 PDF、Word（.docx）、Markdown 和 TXT 文件。");
          if (!file.size || file.size > 25 * 1024 * 1024) throw new Error("文件不能为空，且每份不能超过 25 MB。");
          await uploadKnowledge(file);
          completed++;
        } catch (cause) { failures.push(`${file.name}：${errorMessage(cause)}`); }
      }
    } finally {
      uploadLock.current = false;
      if (mounted.current) {
        setUploading(false); setUploadStatus(`已添加 ${completed} 份文件${failures.length ? `，${failures.length} 份未添加` : ""}。`);
        setUploadErrors(failures); setRevision(value => value + 1);
      }
    }
  }

  async function remove(document: KnowledgeDocument) {
    if (deleting) return;
    setDeleting(document.document_id); setError("");
    try {
      await deleteKnowledgeFile(document.document_id);
      if (mounted.current) {
        if (selected?.id === document.document_id) setSelected(null);
        setRevision(value => value + 1);
      }
    } catch (cause) { if (mounted.current) setError(errorMessage(cause)); }
    finally { if (mounted.current) setDeleting(null); }
  }

  return <section ref={workspace} className="knowledge-workspace" aria-label="知识库文件">
    <WorkspaceToolbar title="知识库文件" onBack={onBack} leading={sidebarToggle} />
    <div className="knowledge-content scroll-content content-column">
      <form className="knowledge-search" onSubmit={event => { event.preventDefault(); setSearch(query.trim()); setRevision(value => value + 1); }}>
        <input className="control" type="search" aria-label="搜索知识库" placeholder="搜索文件名或正文" value={query} maxLength={500} onChange={event => setQuery(event.target.value)} />
        <button className="control control--secondary" type="submit">搜索</button>
        {search ? <button className="control control--secondary" type="button" onClick={() => { setQuery(""); setSearch(""); }}>全部文件</button> : null}
      </form>
      <p className="knowledge-meta">当前账号的所有会话均可查询。支持含文字的 PDF、Word（.docx）、Markdown 和 TXT，每份最多 25 MB。</p>
      {uploadStatus ? <p role="status">{uploadStatus}</p> : null}
      {uploadErrors.map(message => <p role="alert" key={message}>{message}</p>)}
      {error ? <p role="alert">{error} <button className="control control--compact" onClick={() => setRevision(value => value + 1)}>重试</button></p> : null}
      {documents.length ? <GroupedList density="standard">
        {documents.map(document => <article className="knowledge-file standard-control-bar" data-row-surface key={document.document_id}>
          <button className="knowledge-open" data-interaction-owner="row" type="button" aria-label={`查看 ${document.original_filename}`} onClick={() => setSelected({ id: document.document_id, name: document.original_filename, segment: "segment_index" in document ? document.segment_index : 1 })}>
            <ControlRowContent title={document.original_filename} description={"excerpt" in document ? document.excerpt : `${fileSize(document.size_bytes)} · ${document.segment_count} 个内容段`} />
          </button>
          <button className="control control--inline control--icon control--ghost control--danger" data-interaction-owner="self" type="button" disabled={deleting !== null} aria-label={`删除 ${document.original_filename}`} title="删除" onClick={() => void remove(document)}><TrashIcon /></button>
        </article>)}
      </GroupedList> : null}
      {documents.length ? <ListCount total={total} unit="份" label="知识库文件" /> : null}
      {!loading && !error && !documents.length ? <EmptyState title={search ? "没有找到匹配文件" : "上传资料，供会话查询"} /> : null}
      {loading ? <p role="status">正在读取知识库…</p> : null}
      {cursor ? <button className="control control--secondary" type="button" disabled={loading} onClick={() => void more()}>加载更多</button> : null}
      {search && total > documents.length ? <p className="knowledge-meta">当前显示最相关的 {documents.length} 份文件，可补充关键词缩小范围。</p> : null}
    </div>
    <div ref={uploadActions} className="list-floating-actions knowledge-floating-actions">
      <button className="control control--primary primary-action creation-action-button" type="button" disabled={uploading} onClick={() => input.current?.click()}><UploadIcon /><span>{uploading ? "正在上传…" : "上传文件"}</span></button>
    </div>
    <input hidden ref={input} type="file" multiple accept=".pdf,.docx,.md,.txt" aria-label="选择知识库文件" onChange={event => { const files = Array.from(event.target.files ?? []); event.target.value = ""; void upload(files); }} />
    {selected ? <KnowledgePreview key={selected.id} documentId={selected.id} filename={selected.name} initialSegment={selected.segment} onClose={() => setSelected(null)} /> : null}
  </section>;
}

function KnowledgePreview({ documentId, filename, initialSegment, onClose }: {
  documentId: string; filename: string; initialSegment: number; onClose: () => void;
}) {
  const [segment, setSegment] = useState(initialSegment);
  const [reading, setReading] = useState<KnowledgeReading | null>(null);
  const [error, setError] = useState("");
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    setReading(null); setError("");
    void readKnowledgeFile(documentId, segment, controller.signal).then(result => {
      if (!controller.signal.aborted) setReading(result);
    }).catch(cause => { if (!controller.signal.aborted) setError(errorMessage(cause)); });
    return () => controller.abort();
  }, [documentId, segment, retry]);
  return <ContentDialog title={filename} onClose={onClose} bodyClassName="knowledge-preview" actions={reading ? <>
    <button className="control control--compact control--secondary" disabled={segment === 1} onClick={() => setSegment(Math.max(1, segment - 8))}>前文</button>
    <span className="knowledge-meta">{reading.segment_start}–{reading.segment_end} / {reading.document.segment_count} 段</span>
    <button className="control control--compact control--secondary" disabled={reading.next_segment === null} onClick={() => { if (reading.next_segment !== null) setSegment(reading.next_segment); }}>后文</button>
    <a className="control control--compact control--secondary" href={apiUrl(`/knowledge/documents/${encodeURIComponent(documentId)}/content` + (reading.segments[0]?.page_number ? `#page=${reading.segments[0].page_number}` : ""))} target="_blank" rel="noopener noreferrer">打开原件</a>
  </> : undefined}>
    {error ? <p role="alert">{error} <button className="control" onClick={() => setRetry(value => value + 1)}>重试</button></p> : !reading ? <p role="status">正在读取文件…</p> : reading.segments.map(item => <section key={item.segment_index}>
      <h3>{item.page_number ? `第 ${item.page_number} 页 · ` : ""}内容段 {item.segment_index}</h3>
      <p className="knowledge-original-text">{item.content}</p>
    </section>)}
  </ContentDialog>;
}
