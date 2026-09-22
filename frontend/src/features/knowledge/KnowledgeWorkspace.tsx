import { useRef, useState, type ReactNode } from "react";
import { GroupedList } from "../../components/GroupedList";
import { ListChecksIcon, ListTreeIcon } from "../../components/icons";
import { navigationLabels } from "../../components/navigationLabels";
import { WorkspaceToolbar } from "../../components/WorkspaceToolbar";
import { saveBeforeNavigation } from "../../utils/pendingNavigation";
import { SettingsListForwardIcon } from "../settings/SettingsPrimitives";
import { KnowledgeFiles } from "./KnowledgeFiles";
import { LabDictionaryEditor } from "./labDictionary/LabDictionaryEditor";
import type { LabDictionaryDetailPage } from "./labDictionary/labDictionaryDrafts";
import { MedicationCatalog } from "./MedicationCatalog";
import "../../styles/knowledge.css";

const sections = [
  { id: "files", title: "知识库文件", icon: ListChecksIcon },
  { id: "lab-categories", title: navigationLabels.labCategories, icon: ListTreeIcon },
  { id: "lab-items", title: navigationLabels.labItems, icon: ListChecksIcon },
  { id: "medication-catalog", title: "药品目录", icon: ListChecksIcon }
] as const;
type Section = typeof sections[number]["id"];

export function KnowledgeWorkspace({ sidebarToggle, onReportsChanged }: {
  sidebarToggle: ReactNode; onReportsChanged: () => void;
}) {
  const [section, setSection] = useState<Section | null>(null);
  const [detailOpen, setDetailOpen] = useState(false);
  const [detailPage, setDetailPage] = useState<LabDictionaryDetailPage>("root");
  const [detailTitle, setDetailTitle] = useState("");
  const returnFocus = useRef<HTMLElement | null>(null);
  const title = sections.find(item => item.id === section)?.title ?? navigationLabels.knowledge;

  async function select(next: Section | null) {
    if (!await saveBeforeNavigation()) return;
    setDetailOpen(false); setDetailPage("root"); setDetailTitle(""); setSection(next);
  }

  function openDetail() {
    if (detailOpen) return;
    returnFocus.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    setDetailOpen(true);
    requestAnimationFrame(() => document.querySelector<HTMLElement>(".knowledge-workspace .workspace-back-control")?.focus());
  }

  async function back() {
    if (!await saveBeforeNavigation()) return;
    if (detailPage !== "root") { setDetailPage("root"); return; }
    if (detailOpen) {
      setDetailOpen(false);
      requestAnimationFrame(() => { if (returnFocus.current?.isConnected) returnFocus.current.focus(); });
    } else await select(null);
  }

  if (section === "files") return <KnowledgeFiles sidebarToggle={sidebarToggle} onBack={() => void select(null)} />;

  return <section className="knowledge-workspace" aria-label={navigationLabels.knowledge}>
    <WorkspaceToolbar title={detailOpen ? detailTitle || title : title} leading={sidebarToggle}
      onBack={section ? () => void back() : undefined} />
    {!section ? <nav className="knowledge-navigation scroll-content content-column" aria-label="知识库导航">
      <GroupedList density="standard">
        {sections.map(item => <button className="knowledge-navigation-item control control--row" key={item.id}
          onClick={() => void select(item.id)} type="button">
          <item.icon /><span>{item.title}</span><SettingsListForwardIcon />
        </button>)}
      </GroupedList>
    </nav> : <div className="knowledge-catalog settings-content-body" data-detail-open={detailOpen}>
      {section === "medication-catalog" ? <MedicationCatalog detailOpen={detailOpen}
        onOpenDetail={openDetail} onCloseDetail={() => void back()} onDetailTitleChange={setDetailTitle} />
        : <LabDictionaryEditor catalog={section === "lab-items" ? "items" : "categories"}
          detailOpen={detailOpen} detailPage={detailPage} onDetailTitleChange={setDetailTitle}
          onNavigate={setDetailPage} onChangeCatalog={catalog => setSection(catalog === "items" ? "lab-items" : "lab-categories")}
          onOpenDetail={openDetail} onCloseDetail={() => void back()} onReportsChanged={onReportsChanged} />}
    </div>}
  </section>;
}
