import type { ComponentType } from "react";
import { GroupedList } from "../../components/GroupedList";

import {
  GlobeIcon,
  ListChecksIcon,
  ListTreeIcon,
  LockIcon,
  LogOutIcon,
  MessageIcon,
  ServerIcon,
  SlidersIcon,
  UserIcon
} from "../../components/icons";
import type { AccountPanel, SettingsSection } from "./settingsTypes";

export type SettingsNavigationTarget =
  | "members"
  | "account-profile"
  | "account-password"
  | "account-grants"
  | "providers"
  | "defaults"
  | "conversation"
  | "web"
  | "lab-categories"
  | "lab-items";

type NavigationItem = {
  icon: ComponentType<{ className?: string }>;
  label: string;
  target: SettingsNavigationTarget;
};

const settingsNavigationGroups: readonly {
  label: string;
  items: readonly NavigationItem[];
}[] = [
    {
      label: "账号",
      items: [
        { icon: UserIcon, label: "账号资料", target: "account-profile" },
        { icon: LockIcon, label: "密码安全", target: "account-password" },
        { icon: UserIcon, label: "授权管理", target: "account-grants" }
      ]
    },
    {
      label: "模型与工具",
      items: [
        { icon: ServerIcon, label: "模型提供方", target: "providers" },
        { icon: SlidersIcon, label: "默认模型", target: "defaults" },
        { icon: GlobeIcon, label: "联网工具", target: "web" }
      ]
    },
    {
      label: "数据",
      items: [
        { icon: ListTreeIcon, label: "检验分类目录", target: "lab-categories" },
        { icon: ListChecksIcon, label: "检验指标目录", target: "lab-items" }
      ]
    },
    {
      label: "显示",
      items: [
        { icon: UserIcon, label: "健康档案", target: "members" },
        { icon: MessageIcon, label: "聊天设置", target: "conversation" }
      ]
    }
  ];

function navigationTargetIsActive(
  target: SettingsNavigationTarget,
  activeSection: SettingsSection,
  accountPanel: AccountPanel
) {
  if (target === "account-profile") {
    return activeSection === "account" && accountPanel === "profile";
  }
  if (target === "account-password") {
    return activeSection === "account" && accountPanel === "password";
  }
  if (target === "account-grants") {
    return activeSection === "account" && accountPanel === "grants";
  }
  return activeSection === target;
}

export function SettingsNavigation({
  accountPanel,
  activeSection,
  onSelect,
  onSignOut
}: {
  accountPanel: AccountPanel;
  activeSection: SettingsSection;
  onSelect: (target: SettingsNavigationTarget) => void;
  onSignOut: () => void;
}) {
  return (
    <aside className="settings-nav settings-primary-nav scroll-content" aria-label="设置导航">
      <div className="settings-root-list">
        {settingsNavigationGroups.map((group) => (
          <section aria-labelledby={`settings-nav-${group.label}`} className="settings-nav-group" key={group.label}>
            <h2 id={`settings-nav-${group.label}`}>{group.label}</h2>
            <GroupedList className="settings-nav-group-list" density="standard">
              {group.items.map((item) => {
                const active = navigationTargetIsActive(
                  item.target,
                  activeSection,
                  accountPanel
                );
                const Icon = item.icon;
                return (
                  <button
                    aria-current={active ? "page" : undefined}
                    className={active ? "settings-nav-item active" : "settings-nav-item"}
                    key={item.target}
                    onClick={() => onSelect(item.target)}
                    type="button"
                  >
                    <Icon className="settings-nav-icon" />
                    <span>{item.label}</span>
                  </button>
                );
              })}
            </GroupedList>
          </section>
        ))}
      </div>
      <button
        className="control control--secondary control--danger settings-nav-item settings-sign-out-button removal-action-control"
        onClick={onSignOut}
        type="button"
      >
        <LogOutIcon />
        <span>退出登录</span>
      </button>
    </aside>
  );
}
