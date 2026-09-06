import type { Dispatch, RefObject, SetStateAction } from "react";
import {
  ProviderSummary,
  RemoteModel,
  WebAccessSettings
} from "../../api/client";
import { invalidateConnectionTestRequest } from './settingsConnectionRequests';
import {
  type AccountPanel,
  type ConversationSettingsSection,
  type LabCatalog,
  type ProviderConnectionTestState,
  type SettingsMobileLayer,
  type SettingsSection,
  type TestState
} from "./settingsTypes";

type Dependencies = {
  setActiveSection: Dispatch<SetStateAction<SettingsSection>>;
  setAccountPanel: Dispatch<SetStateAction<AccountPanel>>;
  setMobileLayer: Dispatch<SetStateAction<SettingsMobileLayer>>;
  setDetailOpen: Dispatch<SetStateAction<boolean>>;
  providers: ProviderSummary[];
  providerConnectionTestRequestIdsRef: RefObject<Map<string, number>>;
  setConnectionTestStates: Dispatch<SetStateAction<Record<string, ProviderConnectionTestState>>>;
  setProviderPageEntryVersion: Dispatch<SetStateAction<number>>;
  setConversationSection: Dispatch<SetStateAction<ConversationSettingsSection>>;
  webAccess: WebAccessSettings | null;
  webConnectionTestRequestIdsRef: RefObject<Map<string, number>>;
  setWebConnectionTestStates: Dispatch<SetStateAction<Record<string, ProviderConnectionTestState>>>;
  setWebProviderFeedback: Dispatch<SetStateAction<Record<string, TestState>>>;
  activeSection: SettingsSection;
  setSelectedProviderId: Dispatch<SetStateAction<string>>;
  setRemoteModels: Dispatch<SetStateAction<RemoteModel[]>>;
  setModelPickerError: Dispatch<SetStateAction<string>>;
  mobileLayer: SettingsMobileLayer;
};

export function createSettingsNavigationActions({
  setActiveSection,
  setAccountPanel,
  setMobileLayer,
  setDetailOpen,
  providers,
  providerConnectionTestRequestIdsRef,
  setConnectionTestStates,
  setProviderPageEntryVersion,
  setConversationSection,
  webAccess,
  webConnectionTestRequestIdsRef,
  setWebConnectionTestStates,
  setWebProviderFeedback,
  activeSection,
  setSelectedProviderId,
  setRemoteModels,
  setModelPickerError,
  mobileLayer
}: Dependencies) {
  function selectAccountPanel(panel: AccountPanel) {
    setActiveSection("account");
    setAccountPanel(panel);
    setMobileLayer("root");
    setDetailOpen(true);
  }

  function selectProvidersRoot() {
    for (const provider of providers) {
      invalidateConnectionTestRequest(providerConnectionTestRequestIdsRef, provider.provider_id);
    }
    setConnectionTestStates({});
    setProviderPageEntryVersion((current) => current + 1);
    setActiveSection("providers");
    setMobileLayer("provider-list");
    setDetailOpen(false);
  }

  function selectDefaultsRoot() {
    setActiveSection("defaults");
    setMobileLayer("root");
    setDetailOpen(true);
  }

  function selectConversationRoot() {
    setActiveSection("conversation");
    setConversationSection("composer");
    setMobileLayer("conversation-list");
    setDetailOpen(false);
  }

  function selectConversationSection(section: ConversationSettingsSection) {
    setActiveSection("conversation");
    setConversationSection(section);
    setMobileLayer("conversation-list");
    setDetailOpen(true);
  }

  function selectMembersRoot() {
    setActiveSection("members");
    setMobileLayer("root");
    setDetailOpen(true);
  }

  function selectWebRoot() {
    (webAccess?.providers ?? []).forEach((provider) => {
      invalidateConnectionTestRequest(webConnectionTestRequestIdsRef, provider.provider_id);
    });
    setWebConnectionTestStates({});
    setWebProviderFeedback({});
    setActiveSection("web");
    setMobileLayer("root");
    setDetailOpen(true);
  }

  function selectLabCatalogRoot(catalog: LabCatalog) {
    setActiveSection(catalog === "items" ? "lab-items" : "lab-categories");
    setMobileLayer("dictionary-list");
    setDetailOpen(false);
  }

  function openSettingsDetail() {
    if (activeSection === "providers") {
      setMobileLayer("provider-list");
    } else if (activeSection === "conversation") {
      setMobileLayer("conversation-list");
    } else if (activeSection === "lab-categories" || activeSection === "lab-items") {
      setMobileLayer("dictionary-list");
    }
    setDetailOpen(true);
  }

  function selectProvider(providerId: string) {
    setActiveSection("providers");
    setSelectedProviderId(providerId);
    setRemoteModels([]);
    setModelPickerError("");
    setMobileLayer("provider-list");
    setDetailOpen(true);
  }

  function closeSettingsDetail() {
    setDetailOpen(false);
  }

  function settingsMobileLayerTitle() {
    if (mobileLayer === "provider-list") {
      return "模型提供方";
    }
    if (mobileLayer === "conversation-list") {
      return "聊天设置";
    }
    if (mobileLayer === "dictionary-list") {
      return activeSection === "lab-items" ? "检验指标目录" : "检验分类目录";
    }
    return "账号设置";
  }

  function goBackSettingsLayer() {
    if (
      mobileLayer === "provider-list"
      || mobileLayer === "conversation-list"
      || mobileLayer === "dictionary-list"
    ) {
      setMobileLayer("root");
      return;
    }
    setMobileLayer("root");
  }
  return {
    selectAccountPanel,
    selectProvidersRoot,
    selectDefaultsRoot,
    selectConversationRoot,
    selectConversationSection,
    selectMembersRoot,
    selectWebRoot,
    selectLabCatalogRoot,
    openSettingsDetail,
    selectProvider,
    closeSettingsDetail,
    settingsMobileLayerTitle,
    goBackSettingsLayer
  };
}
