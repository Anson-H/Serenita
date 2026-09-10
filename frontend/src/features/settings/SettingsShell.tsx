import type { Dispatch, SetStateAction } from "react";
import { useRef, useState, type ReactNode } from "react";
import { type AuthenticatedSession } from "../../api/client";
import { saveBeforeNavigation } from "../../utils/pendingNavigation";
import { SerialTasks } from "../../utils/serialTasks";
import { useActiveScope } from "../../utils/useActiveScope";
import { useScopedState } from "../../utils/useScopedState";
import { useComposerSubmitShortcut } from "../accountPreferences/composerSubmitShortcut";
import { useContextAssemblyDisplaySettings } from "../accountPreferences/contextAssemblyDisplay";
import { useToolExecutionDisplayTypes } from "../accountPreferences/toolExecutionDisplay";
import type { ModelCatalog } from "../modelConfiguration/modelCatalog";
import { SettingsView } from "./SettingsView";
import { createConversationSettingsActions } from "./conversationSettingsActions";
import { createSettingsNavigationActions } from "./settingsNavigationActions";
import {
  type AccountPanel,
  type ConversationSettingsSection,
  type SettingsMobileLayer,
  type SettingsSection,
} from "./settingsTypes";
import { useAccountSettings } from "./useAccountSettings";
import { useModelsSettings } from "./useModelsSettings";
import { useProviderSettings } from "./useProviderSettings";
import { useWebSettings } from "./useWebSettings";

type SettingsShellProps = {
  accountId: string;
  account: string;
  accountName: string;
  mobileSidebarToggle?: ReactNode;
  onSignOut: () => void;
  onAccountProfileChange: (session: AuthenticatedSession) => void;
  modelCatalog: ModelCatalog;
  onModelsChanged: Dispatch<SetStateAction<ModelCatalog>>;
  refreshModels: (isRelevant?: () => boolean) => Promise<void>;
  onReportsChanged: () => void;
};

export function SettingsShell({
  accountId,
  account,
  accountName,
  mobileSidebarToggle,
  onSignOut,
  onAccountProfileChange,
  modelCatalog,
  onModelsChanged,
  refreshModels,
  onReportsChanged,
}: SettingsShellProps) {
  const [composing, setComposing] = useState(false);
  const isCurrentScope = useActiveScope(accountId);
  const serialTasks = useRef(new SerialTasks());
  const [activeSection, setActiveSection] = useScopedState<SettingsSection>(
    "account",
    isCurrentScope,
  );
  const [accountPanel, setAccountPanel] = useScopedState<AccountPanel>(
    "profile",
    isCurrentScope,
  );
  const [conversationSection, setConversationSection] =
    useScopedState<ConversationSettingsSection>("composer", isCurrentScope);
  const [mobileLayer, setMobileLayer] = useScopedState<SettingsMobileLayer>(
    "root",
    isCurrentScope,
  );
  const [detailOpen, setDetailOpen] = useScopedState(false, isCurrentScope);
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
  } = useAccountSettings({
    accountId,
    account,
    accountName,
    composing,
    isCurrentScope,
    serialTasks,
    onAccountProfileChange,
  });

  const {
    providers,
    selectedProviderId,
    setSelectedProviderId,
    connectionTestStates,
    setConnectionTestStates,
    setProviderPageEntryVersion,
    providerConnectionTestRequestsRef,
    selectedProvider,
    selectedDraft,
    selectedProviderFeedback,
    updateDraft,
    revealModelCredential,
    testProviderConnection,
    autoSaveProviderDraft,
    setTestStates,
    loadError: providerLoadError,
  } = useProviderSettings({
    accountId,
    composing,
    activeSection,
    isCurrentScope,
    serialTasks,
  });

  const {
    remoteModels,
    setRemoteModels,
    modelPickerOpen,
    setModelPickerOpen,
    modelPickerLoading,
    modelPickerError,
    setModelPickerError,
    addedModels,
    addingRemoteModelIds,
    probingModelIds,
    savingModelIds,
    defaultModelItems,
    openAddModelModal,
    retryLoadRemoteModels,
    addRemoteModel,
    probeAddedModel,
    updateAddedModel,
    deleteAddedModel,
    updateDefaultModel,
    loadError: modelsLoadError,
  } = useModelsSettings({
    modelCatalog,
    onModelsChanged,
    refreshModels,
    isCurrentScope,
    serialTasks,
    selectedProvider,
    selectedDraft,
    autoSaveProviderDraft,
    setTestStates,
  });

  const {
    webAccess,
    webApiUrls,
    webApiKeys,
    webFeedback,
    webProviderFeedback,
    setWebProviderFeedback,
    webConnectionTestStates,
    setWebConnectionTestStates,
    webConnectionTestRequestsRef,
    updateWebApiUrl,
    saveWebApiUrl,
    updateWebApiKey,
    revealWebCredential,
    updateWebSettings,
    testWebProvider,
    loadError: webLoadError,
  } = useWebSettings({ accountId, composing, isCurrentScope, serialTasks });

  const loadError = providerLoadError || modelsLoadError || webLoadError;

  const composerSubmitShortcut = useComposerSubmitShortcut(accountId);
  const contextDisplaySettings = useContextAssemblyDisplaySettings(accountId);
  const toolDisplayTypes = useToolExecutionDisplayTypes(accountId);
  const selectedProviderModels = selectedProvider
    ? addedModels.filter(
        (model) => model.provider_id === selectedProvider.provider_id,
      )
    : [];

  const {
    selectAccountPanel,
    selectProvidersRoot,
    selectDefaultsRoot,
    selectConversationRoot,
    selectConversationSection,
    selectMembersRoot,
    selectMedicationCatalogRoot,
    selectThemeRoot,
    selectWebRoot,
    selectLabCatalogRoot,
    openSettingsDetail,
    selectProvider,
    closeSettingsDetail,
    settingsMobileLayerTitle,
    goBackSettingsLayer,
  } = createSettingsNavigationActions({
    setActiveSection,
    setAccountPanel,
    setMobileLayer,
    setDetailOpen,
    providers,
    providerConnectionTestRequestsRef,
    setConnectionTestStates,
    setProviderPageEntryVersion,
    setConversationSection,
    webAccess,
    webConnectionTestRequestsRef,
    setWebConnectionTestStates,
    setWebProviderFeedback,
    activeSection,
    setSelectedProviderId,
    setRemoteModels,
    setModelPickerError,
    mobileLayer,
  });
  const {
    updateContextDisplayType,
    updateComposerSubmitShortcut,
    updateBaseContextDisplayMode,
    updateShowContextWindowUsage,
    updateShowRelatedContent,
    updateShowTokenUsage,
    updateShowModelIdentity,
    updateToolDisplayType,
  } = createConversationSettingsActions({
    accountId,
    contextDisplaySettings,
    toolDisplayTypes,
  });

  return (
    <div
      style={{ display: "contents" }}
      onCompositionStartCapture={() => setComposing(true)}
      onCompositionEndCapture={() => setComposing(false)}
    >
      <SettingsView
        accountDraft={accountDraft}
        accountFeedback={accountFeedback}
        accountPanel={accountPanel}
        activeSection={activeSection}
        addedModels={addedModels}
        addRemoteModel={addRemoteModel}
        addingRemoteModelIds={addingRemoteModelIds}
        changePassword={changePassword}
        confirmPassword={confirmPassword}
        conversationSection={conversationSection}
        composerSubmitShortcut={composerSubmitShortcut}
        baseContextDisplayModes={contextDisplaySettings.baseModes}
        contextDisplayTypes={contextDisplaySettings.visibleContextTypes}
        showContextWindowUsage={contextDisplaySettings.showContextWindowUsage}
        showRelatedContent={contextDisplaySettings.showRelatedContent}
        showTokenUsage={contextDisplaySettings.showTokenUsage}
        showModelIdentity={contextDisplaySettings.showModelIdentity}
        toolDisplayTypes={toolDisplayTypes}
        currentPassword={currentPassword}
        deleteAddedModel={deleteAddedModel}
        defaultModelItems={defaultModelItems}
        defaultModelOptions={addedModels}
        detailOpen={detailOpen}
        closeSettingsDetail={() => {
          void saveBeforeNavigation().then((saved) => {
            if (saved) closeSettingsDetail();
          });
        }}
        goBackSettingsLayer={() => {
          void saveBeforeNavigation().then((saved) => {
            if (saved) goBackSettingsLayer();
          });
        }}
        loadError={loadError}
        mobileLayer={mobileLayer}
        mobileSidebarToggle={mobileSidebarToggle}
        modelPickerError={modelPickerError}
        modelPickerLoading={modelPickerLoading}
        modelPickerOpen={modelPickerOpen}
        probingModelIds={probingModelIds}
        probeAddedModel={probeAddedModel}
        nameDraft={nameDraft}
        newPassword={newPassword}
        openAddModelModal={openAddModelModal}
        onReportsChanged={onReportsChanged}
        onSignOut={() => {
          void saveBeforeNavigation().then((saved) => {
            if (saved) onSignOut();
          });
        }}
        providerConnectionStates={connectionTestStates}
        providers={providers}
        remoteModels={remoteModels}
        selectedDraft={selectedDraft}
        selectedProvider={selectedProvider}
        selectedProviderFeedback={selectedProviderFeedback}
        selectedProviderId={selectedProviderId}
        selectedProviderModels={selectedProviderModels}
        selectAccountPanel={(value) => {
          void saveBeforeNavigation().then((saved) => {
            if (saved) selectAccountPanel(value);
          });
        }}
        selectConversationRoot={() => {
          void saveBeforeNavigation().then((saved) => {
            if (saved) selectConversationRoot();
          });
        }}
        selectConversationSection={(value) => {
          void saveBeforeNavigation().then((saved) => {
            if (saved) selectConversationSection(value);
          });
        }}
        selectDefaultsRoot={() => {
          void saveBeforeNavigation().then((saved) => {
            if (saved) selectDefaultsRoot();
          });
        }}
        selectLabCatalogRoot={(value) => {
          void saveBeforeNavigation().then((saved) => {
            if (saved) selectLabCatalogRoot(value);
          });
        }}
        openSettingsDetail={() => {
          void saveBeforeNavigation().then((saved) => {
            if (saved) openSettingsDetail();
          });
        }}
        selectProvider={(value) => {
          void saveBeforeNavigation().then((saved) => {
            if (saved) selectProvider(value);
          });
        }}
        selectProvidersRoot={() => {
          void saveBeforeNavigation().then((saved) => {
            if (saved) selectProvidersRoot();
          });
        }}
        setConfirmPassword={setConfirmPassword}
        setCurrentPassword={setCurrentPassword}
        setAccountDraft={setAccountDraft}
        setModelPickerOpen={setModelPickerOpen}
        setNameDraft={setNameDraft}
        setNewPassword={setNewPassword}
        retryLoadRemoteModels={retryLoadRemoteModels}
        revealModelCredential={revealModelCredential}
        revealWebCredential={revealWebCredential}
        settingsMobileLayerTitle={settingsMobileLayerTitle}
        testProviderConnection={testProviderConnection}
        savingModelIds={savingModelIds}
        updateDefaultModel={updateDefaultModel}
        updateBaseContextDisplayMode={updateBaseContextDisplayMode}
        updateComposerSubmitShortcut={updateComposerSubmitShortcut}
        updateContextDisplayType={updateContextDisplayType}
        updateShowRelatedContent={updateShowRelatedContent}
        updateShowContextWindowUsage={updateShowContextWindowUsage}
        updateShowTokenUsage={updateShowTokenUsage}
        updateShowModelIdentity={updateShowModelIdentity}
        updateToolDisplayType={updateToolDisplayType}
        updateDraft={updateDraft}
        updateAddedModel={updateAddedModel}
        updateWebApiKey={updateWebApiKey}
        updateWebSettings={updateWebSettings}
        selectWebRoot={() => {
          void saveBeforeNavigation().then((saved) => {
            if (saved) selectWebRoot();
          });
        }}
        selectMedicationCatalogRoot={() => {void saveBeforeNavigation().then(saved=>{if(saved)selectMedicationCatalogRoot();});}}
        selectMembersRoot={() => {
          void saveBeforeNavigation().then((saved) => {
            if (saved) selectMembersRoot();
          });
        }}
        selectThemeRoot={() => {
          void saveBeforeNavigation().then((saved) => {
            if (saved) selectThemeRoot();
          });
        }}
        webAccess={webAccess}
        webApiUrls={webApiUrls}
        webApiKeys={webApiKeys}
        webFeedback={webFeedback}
        webConnectionTestStates={webConnectionTestStates}
        webProviderFeedback={webProviderFeedback}
        saveWebApiUrl={saveWebApiUrl}
        testWebProvider={testWebProvider}
        updateWebApiUrl={updateWebApiUrl}
      />
    </div>
  );
}
