import { AuthSession, ConversationSummary } from "../api/client";
import {
  APP_PATH,
  FAVORITES_PATH,
  SETTING_PATH,
  type RoutePath
} from "./routes";
import {
  FavoriteNavIcon,
  HealthRecordIcon,
  LifestyleScenarioIcon,
  PlusIcon,
  ReportScenarioIcon,
  SettingsNavIcon,
  SidebarCloseIcon,
  TrashIcon
} from "../components/icons";
import {
  scenarioLabel,
  type ScenarioTab
} from "../features/conversations/workspaceTypes";

const sidebarScenarioTabs: ScenarioTab[] = ["reports", "lifestyle"];

type SidebarProps = {
  activeScenario: ScenarioTab;
  activeView: "home" | "health";
  conversations: ConversationSummary[];
  currentSession: Extract<AuthSession, { authenticated: true }>;
  currentSessionId: string | null;
  onCloseMobileSidebar: () => void;
  onCollapseSidebar: () => void;
  onDeleteConversation: (sessionId: string) => void;
  onNavigate: (path: RoutePath) => void;
  onOpenConversation: (sessionId: string) => void;
  onScenarioChange: (scenario: ScenarioTab) => void;
  onStartConversation: () => void;
  onSwitchView: (view: "home" | "health") => void;
  route: RoutePath;
};

export function Sidebar({
  activeScenario,
  activeView,
  conversations,
  currentSession,
  currentSessionId,
  onCloseMobileSidebar,
  onCollapseSidebar,
  onDeleteConversation,
  onNavigate,
  onOpenConversation,
  onScenarioChange,
  onStartConversation,
  onSwitchView,
  route
}: SidebarProps) {
  function openScenarioFromSidebar(scenario: ScenarioTab) {
    onNavigate(APP_PATH);
    onSwitchView("home");
    onScenarioChange(scenario);
  }

  return (
    <aside
      aria-label="主导航"
      className="patient-sidebar"
    >
      <section className="sidebar-header">
        <div className="brand-row">
          <div className="brand-name">
            <span>Serenita</span>
          </div>
          <button
            aria-label="折叠侧边栏"
            className="sidebar-collapse-button"
            onClick={onCollapseSidebar}
            title="折叠侧边栏"
            type="button"
          >
            <SidebarCloseIcon />
          </button>
          <button
            aria-label="关闭侧边栏"
            className="mobile-sidebar-close-button"
            onClick={onCloseMobileSidebar}
            title="关闭侧边栏"
            type="button"
          >
            <SidebarCloseIcon />
          </button>
        </div>
      </section>

      <div className="sidebar-content">
        <nav className="global-nav">
          <div className="sidebar-scenario-nav" role="group" aria-label="场景切换">
            {sidebarScenarioTabs.map((scenario) => {
              const Icon = scenario === "reports" ? ReportScenarioIcon : LifestyleScenarioIcon;
              const isActiveScenario = route === APP_PATH && activeView === "home" && activeScenario === scenario;

              return (
                <button
                  aria-label={`切换到${scenarioLabel(scenario)}`}
                  className={isActiveScenario ? "sidebar-scenario-tab active" : "sidebar-scenario-tab"}
                  key={scenario}
                  onClick={() => openScenarioFromSidebar(scenario)}
                  type="button"
                >
                  <span className="scenario-icon-frame">
                    <Icon />
                  </span>
                  <span className="nav-label">{scenarioLabel(scenario)}</span>
                </button>
              );
            })}
          </div>
          <button
            aria-label="开启新对话"
            className="primary-action"
            onClick={onStartConversation}
            title="开启新对话"
            type="button"
          >
            <PlusIcon />
            <span className="nav-label">开启新对话</span>
          </button>
        </nav>

        <section className="conversation-list" aria-label="会话列表">
          {conversations.length ? (
            conversations.map((conversation) => (
              <div className="conversation-item-row" key={conversation.session_id}>
                <div className={conversation.session_id === currentSessionId ? "conversation-item-frame active" : "conversation-item-frame"}>
                  <button
                    aria-current={conversation.session_id === currentSessionId ? "page" : undefined}
                    className="conversation-title-button"
                    onClick={() => onOpenConversation(conversation.session_id)}
                    type="button"
                  >
                    {conversation.title}
                  </button>
                  <button
                    aria-label={`删除会话：${conversation.title}`}
                    className="conversation-delete-button"
                    onClick={() => onDeleteConversation(conversation.session_id)}
                    type="button"
                    title="删除会话"
                  >
                    <TrashIcon />
                  </button>
                </div>
              </div>
            ))
          ) : (
            <span className="message-meta conversation-list-empty">暂无历史会话</span>
          )}
        </section>

        <div className="sidebar-bottom">
          <nav className="secondary-nav" aria-label="辅助导航">
            <button
              aria-label="原始文件"
              className={route === APP_PATH && activeView === "health" ? "nav-item active" : "nav-item"}
              onClick={() => {
                onNavigate(APP_PATH);
                onSwitchView("health");
              }}
              title="原始文件"
              type="button"
            >
              <HealthRecordIcon />
              <span className="nav-label">原始文件</span>
            </button>
            <button
              aria-label="我的收藏"
              className={route === FAVORITES_PATH ? "nav-item active" : "nav-item"}
              onClick={() => onNavigate(FAVORITES_PATH)}
              title="我的收藏"
              type="button"
            >
              <FavoriteNavIcon />
              <span className="nav-label">我的收藏</span>
            </button>
          </nav>

          <section className="user-summary" aria-label="当前账号">
            <button
              aria-label="账号设置"
              className={route === SETTING_PATH ? "account-button active" : "account-button"}
              onClick={() => onNavigate(SETTING_PATH)}
              title={currentSession.user_name}
              type="button"
            >
              <span className="account-avatar" aria-hidden="true">
                {currentSession.user_name.slice(0, 1).toUpperCase()}
              </span>
              <span className="account-copy">
                <strong>{currentSession.user_name}</strong>
              </span>
              <SettingsNavIcon />
            </button>
          </section>
        </div>
      </div>
    </aside>
  );
}
