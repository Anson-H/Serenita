import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import assert from "node:assert/strict";

const root = dirname(dirname(fileURLToPath(import.meta.url)));
const read = (path) => readFileSync(join(root, path), "utf8");

const homeWorkspace = read("src/features/conversations/HomeWorkspace.tsx");
const sidebar = read("src/app/Sidebar.tsx");
const icons = read("src/components/icons.tsx");
const patientShell = read("src/app/PatientShell.tsx");
const routeShell = read("src/app/WorkspaceRouteShell.tsx");
const routeContent = read("src/features/conversations/WorkspaceRouteContent.tsx");

assert(
  !homeWorkspace.includes('className="workspace-tabs"'),
  "home workspace should not render the scene switcher above the conversation"
);

assert(
  sidebar.includes('<section className="sidebar-header"') &&
    sidebar.includes('<div className="sidebar-content">') &&
    sidebar.indexOf('className="sidebar-header"') < sidebar.indexOf('className="sidebar-content"') &&
    sidebar.indexOf('className="sidebar-content"') < sidebar.indexOf('className="global-nav"') &&
    sidebar.indexOf('className="sidebar-content"') < sidebar.indexOf('className="conversation-list"') &&
    sidebar.indexOf('className="sidebar-content"') < sidebar.indexOf('className="sidebar-bottom"'),
  "patient sidebar should split into a header region and a separate content region"
);

assert(
  sidebar.includes('className="sidebar-scenario-nav"') &&
    sidebar.includes("sidebarScenarioTabs.map") &&
    sidebar.includes("openScenarioFromSidebar(scenario)"),
  "sidebar should render the scene switcher and route scenario clicks through the sidebar handler"
);

assert(
  !sidebar.includes('route === APP_PATH && activeView === "home" ?') &&
    sidebar.includes("onNavigate(APP_PATH);") &&
    sidebar.includes('onSwitchView("home");') &&
    sidebar.includes("onScenarioChange(scenario);"),
  "sidebar scene switcher should be available on every route and return to the home workspace scenario"
);

assert(
  sidebar.includes('const sidebarScenarioTabs: ScenarioTab[] = ["reports", "lifestyle"];') &&
    !sidebar.includes('sidebarScenarioTabs: ScenarioTab[] = ["home"'),
  "sidebar scene switcher should omit the home button"
);

assert(
  sidebar.indexOf('className="sidebar-scenario-nav"') < sidebar.indexOf('aria-label="开启新对话"'),
  "sidebar scene switcher should render above the new conversation button"
);

assert(
  sidebar.includes('aria-label="原始文件"') &&
    sidebar.includes('title="原始文件"') &&
    sidebar.includes('<span className="nav-label">原始文件</span>') &&
    !sidebar.includes("健康档案") &&
    homeWorkspace.includes("<span>原始文件</span>") &&
    homeWorkspace.includes("<h1>原始文件暂作为占位入口</h1>"),
  "raw-file entry should be labeled 原始文件 instead of 健康档案"
);

assert(
  sidebar.includes("ReportScenarioIcon") &&
    sidebar.includes("LifestyleScenarioIcon") &&
    sidebar.includes("<Icon />") &&
    sidebar.includes('className="scenario-icon-frame"'),
  "sidebar scene switcher should render clear leading icons for reports and lifestyle"
);

assert(
  icons.includes("export function HealthRecordIcon()") &&
    icons.includes('d="M6.5 3.5h7.2L18 7.8v12.7H6.5v-17Z"') &&
    icons.includes("export function ReportScenarioIcon()") &&
    icons.includes("<rect") &&
    !icons.includes('d="M6.5 19.5V4.5h8.2l2.8 2.8v12.2h-11Z"') &&
    !icons.includes('d="m7.2 12.2 4.8-4.8 4.8 4.8"'),
  "report scene icon should use obvious bar-chart geometry while health record keeps the original file icon"
);

assert(
  icons.includes("export function LifestyleScenarioIcon()") &&
    icons.includes('d="M12 20c4.2-1.9 6.5-5.1 6.5-9.4V5.5h-5.1C9.1 5.5 6 8.6 6 12.9V18h4.7"') &&
    !icons.includes('d="M7.8 12h2.5l1-2.2 1.7 4.2 1-2h2.2"'),
  "lifestyle scene icon should use a calm leaf shape instead of a heartbeat line"
);

assert(
  patientShell.includes("activeScenario") &&
    patientShell.includes("onScenarioChange") &&
    routeShell.includes("activeScenario") &&
    routeShell.includes("onScenarioChange"),
  "patient shell and route shell should pass scenario state through to the sidebar"
);

assert(
  routeContent.includes("activeScenario={pageState.activeScenario}") &&
    routeContent.includes("onScenarioChange={lifecycle.changeScenario}"),
  "workspace route content should wire draft-aware scenario changes into the shell"
);
