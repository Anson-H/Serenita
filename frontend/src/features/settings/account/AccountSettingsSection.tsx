import { navigationLabels } from "../../../components/navigationLabels";
import { NotificationSettings } from "./NotificationSettings";
import { GroupedList } from "../../../components/GroupedList";
import {
  LockIcon
} from "../../../components/icons";
import { SecretInput } from "../../../components/SecretInput";
import { useStatusNotification } from "../../../components/StatusNotificationCenter";
import { keepTextControlFocused, syncCommittedText } from "../../../utils/inputMethod";
import { MemberGrantsPanel } from "../../members/MemberSettings";

import { useAccountSettings } from "./useAccountSettings";
import { SettingsSectionLayout } from "../SettingsSectionLayout";
import { useSettingsNavigation, type SettingsSession } from "../SettingsNavigationContext";
import type { AuthenticatedSession } from "../../../api/auth/authTypes";

export function AccountSettingsSection({ session, account, accountName, onAccountProfileChange }: {
  session: SettingsSession; account: string; accountName: string; onAccountProfileChange: (session: AuthenticatedSession) => void;
}) {
  const { actions: { activeSection, accountPanel } } = useSettingsNavigation();
  const {
    accountDraft,
    setAccountDraft,
    nameDraft,
    setNameDraft,
    currentPassword,
    setCurrentPassword,
    newPassword,
    setNewPassword,
    confirmPassword,
    setConfirmPassword,
    accountFeedback,
    changePassword,
  } = useAccountSettings({ ...session, account, accountName, onAccountProfileChange });

  useStatusNotification(accountFeedback.status === "error" ? accountFeedback.message : "", { id: "settings-account-status", title: "更新失败", tone: "error", durationMs: 3000 });
  if (activeSection !== "account") return null;
  const title = accountPanel === "profile" ? navigationLabels.accountProfile : accountPanel === "password" ? navigationLabels.accountPassword : accountPanel === "notifications" ? navigationLabels.notifications : navigationLabels.accountGrants;
  return <SettingsSectionLayout title={title}><div className="settings-detail-column">
    {accountPanel === "notifications" ? <NotificationSettings /> : null}
    {accountPanel === "grants" ? <MemberGrantsPanel /> : null}
    {activeSection === "account" && accountPanel === "profile" ? (
      <section className="settings-section">
        <GroupedList layout="fields" density="standard">
          <label className="field-row">
            用户标识
            <input
              autoCapitalize="none"
              autoComplete="username"
              spellCheck={false}
              value={accountDraft}
              onChange={(event) => setAccountDraft(event.target.value)}
            />
          </label>
          <label className="field-row">
            账号名称
            <input value={nameDraft} onChange={(event) => setNameDraft(event.target.value)} onCompositionEnd={(event) => syncCommittedText(event, setNameDraft)} />
          </label>
        </GroupedList>
      </section>
    ) : null}

    {activeSection === "account" && accountPanel === "password" ? (
      <form className="settings-section password-section" onSubmit={changePassword}>
        <GroupedList layout="fields" density="standard">
          <div className="secret-field field-row">
            <label htmlFor="settings-current-password">当前密码</label>
            <SecretInput
              autoComplete="current-password"
              id="settings-current-password"
              labelForAction="当前密码"
              name="current-password"
              value={currentPassword}
              onChange={(event) => setCurrentPassword(event.target.value)}
              onCompositionEnd={(event) => syncCommittedText(event, setCurrentPassword)}
            />
          </div>
          <div className="secret-field field-row">
            <label htmlFor="settings-new-password">新密码</label>
            <SecretInput
              autoComplete="new-password"
              id="settings-new-password"
              labelForAction="新密码"
              name="new-password"
              value={newPassword}
              onChange={(event) => setNewPassword(event.target.value)}
              onCompositionEnd={(event) => syncCommittedText(event, setNewPassword)}
            />
          </div>
          <div className="secret-field field-row">
            <label htmlFor="settings-confirm-password">确认新密码</label>
            <SecretInput
              autoComplete="new-password"
              id="settings-confirm-password"
              labelForAction="确认新密码"
              name="confirm-password"
              value={confirmPassword}
              onChange={(event) => setConfirmPassword(event.target.value)}
              onCompositionEnd={(event) => syncCommittedText(event, setConfirmPassword)}
            />
          </div>
        </GroupedList>
        <button className="control control--primary command-button control-primary password-update-button" onMouseDown={keepTextControlFocused} type="submit">
          <LockIcon />
          <span>更新密码</span>
        </button>
      </form>
    ) : null}

  </div></SettingsSectionLayout>;
}
