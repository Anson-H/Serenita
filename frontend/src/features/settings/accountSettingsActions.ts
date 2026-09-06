import type { Dispatch, RefObject, SetStateAction } from "react";
import { FormEvent } from "react";
import {
  apiClient,
  type AuthenticatedSession
} from "../../api/client";
import { formTextValue } from "../../utils/inputMethod";
import { SerialTasks } from "../../utils/serialTasks";
import {
  type TestState
} from "./settingsTypes";

type Dependencies = {
  serialTasks: RefObject<SerialTasks>;
  isCurrentScope: () => boolean;
  accountSaveRequestIdRef: RefObject<number>;
  onAccountProfileChange: (session: AuthenticatedSession) => void;
  setAccountDraft: Dispatch<SetStateAction<string>>;
  setNameDraft: Dispatch<SetStateAction<string>>;
  setAccountFeedback: Dispatch<SetStateAction<TestState>>;
  currentPassword: string;
  newPassword: string;
  confirmPassword: string;
  setCurrentPassword: Dispatch<SetStateAction<string>>;
  setNewPassword: Dispatch<SetStateAction<string>>;
  setConfirmPassword: Dispatch<SetStateAction<string>>;
};

export function createAccountSettingsActions({
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
  setConfirmPassword
}: Dependencies) {
  async function autoSaveAccountProfile(
    trimmedAccount: string,
    trimmedName: string,
    requestId: number
  ) {
    try {
      const result = await serialTasks.current.run("account", () => apiClient.updateAccount(trimmedAccount, trimmedName), isCurrentScope);
      if (isCurrentScope() && requestId === accountSaveRequestIdRef.current) {
        onAccountProfileChange(result);
        setAccountDraft(result.account);
        setNameDraft(result.account_name);
        setAccountFeedback({ status: "idle", message: "" });
      }
    } catch (error) {
      if (requestId === accountSaveRequestIdRef.current) {
        setAccountFeedback({
          status: "error",
          message: error instanceof Error ? error.message : "保存失败。"
        });
      }
    }
  }

  async function changePassword(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const submittedCurrentPassword = formTextValue(event.currentTarget, "current-password", currentPassword);
    const submittedNewPassword = formTextValue(event.currentTarget, "new-password", newPassword);
    const submittedConfirmPassword = formTextValue(event.currentTarget, "confirm-password", confirmPassword);
    if (!submittedCurrentPassword.trim()) {
      setAccountFeedback({
        status: "error",
        message: "请输入当前密码。"
      });
      return;
    }
    if (!submittedNewPassword.trim()) {
      setAccountFeedback({
        status: "error",
        message: "新密码不能为空。"
      });
      return;
    }
    if (submittedNewPassword !== submittedConfirmPassword) {
      setAccountFeedback({
        status: "error",
        message: "两次输入的新密码不一致。"
      });
      return;
    }

    try {
      const result = await apiClient.changePassword(
        submittedCurrentPassword,
        submittedNewPassword,
        submittedConfirmPassword
      );
      setCurrentPassword("");
      setNewPassword("");
      setConfirmPassword("");
      setAccountFeedback({
        status: "success",
        message: result.message
      });
    } catch (error) {
      setAccountFeedback({
        status: "error",
        message: error instanceof Error ? error.message : "密码更新失败。"
      });
    }
  }
  return {
    autoSaveAccountProfile,
    changePassword
  };
}
