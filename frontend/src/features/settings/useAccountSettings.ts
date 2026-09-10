import { useEffect, useRef } from "react";
import { type AuthenticatedSession } from "../../api/client";
import { SerialTasks } from "../../utils/serialTasks";
import { useResourceAutosave } from "../../utils/useResourceAutosave";
import { useScopedState } from "../../utils/useScopedState";
import { createAccountSettingsActions } from "./accountSettingsActions";
import {
  accountIdentifierPattern,
  accountNameLength,
  settingsAutoSaveDelayMs,
  type TestState,
} from "./settingsTypes";

export function useAccountSettings({
  accountId,
  account,
  accountName,
  composing,
  isCurrentScope,
  serialTasks,
  onAccountProfileChange,
}: {
  accountId: string;
  account: string;
  accountName: string;
  composing: boolean;
  isCurrentScope: () => boolean;
  serialTasks: React.RefObject<SerialTasks>;
  onAccountProfileChange: (value: AuthenticatedSession) => void;
}) {
  const [accountDraft, setAccountDraft] = useScopedState(
    account,
    isCurrentScope,
  );

  const [nameDraft, setNameDraft] = useScopedState(accountName, isCurrentScope);

  const [currentPassword, setCurrentPassword] = useScopedState(
    "",
    isCurrentScope,
  );

  const [newPassword, setNewPassword] = useScopedState("", isCurrentScope);

  const [confirmPassword, setConfirmPassword] = useScopedState(
    "",
    isCurrentScope,
  );

  const [accountFeedback, setAccountFeedback] = useScopedState<TestState>(
    {
      status: "idle",
      message: "",
    },
    isCurrentScope,
  );

  const previousAccountRef = useRef(account);

  const previousAccountNameRef = useRef(accountName);

  const accountSaveRequestIdRef = useRef(0);

  useEffect(() => {
    const previousAccount = previousAccountRef.current;
    previousAccountRef.current = account;
    setAccountDraft((current) =>
      current === previousAccount ? account : current,
    );
  }, [account]);

  useEffect(() => {
    const previousAccountName = previousAccountNameRef.current;
    previousAccountNameRef.current = accountName;
    setNameDraft((current) =>
      current === previousAccountName ? accountName : current,
    );
  }, [accountName]);

  const { autoSaveAccountProfile, changePassword } =
    createAccountSettingsActions({
      serialTasks,
      isCurrentScope,
      accountSaveRequestIdRef,
      onAccountProfileChange,
      setAccountDraft,
      setNameDraft,
      setAccountFeedback,
      currentPassword,
      newPassword,
      confirmPassword,
      setCurrentPassword,
      setNewPassword,
      setConfirmPassword,
    });

  useResourceAutosave(
    [
      {
        key: `${accountId}:account`,
        server: { account, name: accountName },
        draft: { account: accountDraft, name: nameDraft },
        save: async (value) => {
          const trimmedAccount = value.account.trim(),
            trimmedName = value.name.trim();
          if (!accountIdentifierPattern.test(trimmedAccount))
            throw new Error(
              "用户标识只能包含字母、数字、下划线和短横线，长度不超过 20。",
            );
          if (trimmedAccount.toLowerCase() === "all_users")
            throw new Error("该用户标识不可使用。");
          if (!trimmedName || accountNameLength(trimmedName) > 50)
            throw new Error("账号名称须为 1 至 50 个字符。");
          const result = await autoSaveAccountProfile(
            trimmedAccount,
            trimmedName,
            ++accountSaveRequestIdRef.current,
          );
          if (!result) throw new Error("账号信息保存失败，草稿已保留。");
          return { account: result.account, name: result.account_name };
        },
        onError: (message) => setAccountFeedback({ status: "error", message }),
      },
    ],
    composing,
    settingsAutoSaveDelayMs,
  );

  return {
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
  };
}
