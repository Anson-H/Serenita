import { navigationLabels } from "../../components/navigationLabels";
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
  | "theme"
  | "members"
  | "account-profile"
  | "account-password"
  | "account-grants"
  | "account-notifications"
  | "providers"
  | "defaults"
  | "conversation"
  | "web"
  | "lab-categories"
  | "lab-items"
  | "medication-catalog";

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
      label: "账号安全",
      items: [
        { icon: UserIcon, label: navigationLabels.accountProfile, target: "account-profile" },
        { icon: LockIcon, label: navigationLabels.accountPassword, target: "account-password" },
        { icon: UserIcon, label: navigationLabels.accountGrants, target: "account-grants" }
      ]
    },
    {
      label: navigationLabels.notifications,
      items: [
        { icon: MessageIcon, label: navigationLabels.notifications, target: "account-notifications" }
      ]
    },
    {
      label: "模型与工具",
      items: [
        { icon: ServerIcon, label: navigationLabels.providers, target: "providers" },
        { icon: SlidersIcon, label: navigationLabels.defaults, target: "defaults" },
        { icon: GlobeIcon, label: navigationLabels.web, target: "web" }
      ]
    },
    {
      label: "数据",
      items: [
        { icon: ListTreeIcon, label: navigationLabels.labCategories, target: "lab-categories" },
        { icon: ListChecksIcon, label: navigationLabels.labItems, target: "lab-items" },
        { icon: ListChecksIcon, label: "药品目录", target: "medication-catalog" }
      ]
    },
    {
      label: "显示",
      items: [
        { icon: SlidersIcon, label: navigationLabels.theme, target: "theme" },
        { icon: UserIcon, label: navigationLabels.health, target: "members" },
        { icon: MessageIcon, label: navigationLabels.conversation, target: "conversation" }
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
  if (target === "account-notifications") return activeSection === "account" && accountPanel === "notifications";
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
