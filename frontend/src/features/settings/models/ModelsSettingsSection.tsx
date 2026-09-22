import { createDefaultModelActions } from "./defaultModelActions";
import { ModelServiceStatus } from "../../modelConfiguration/models/ModelServiceStatus";
import { isModelAvailable } from "../../modelConfiguration/modelEligibility";
import { AddedModelList } from "../../modelConfiguration/models/AddedModelList";
import { ProviderList } from "../../modelConfiguration/providers/ProviderList";
import { ProviderDetail } from "../../modelConfiguration/providers/ProviderDetail";
import { ModelPickerDialog } from "../../modelConfiguration/models/ModelPickerDialog";
import { CustomProviderDialog } from "../../modelConfiguration/providers/CustomProviderDialog";
import { SerenitaProviderPanel } from "./SerenitaProviderPanel";
import { eligibleForDefault, supportedEmbeddingModalities, modalityLabels } from "../../modelConfiguration/modelEligibility";
import { navigationLabels } from "../../../components/navigationLabels";
import { EmptyState } from "../../../components/EmptyState";
import { useEffect, useState, useRef } from "react";
import type { ProviderSummary } from "../../../api/models/modelTypes";

import { GroupedList } from "../../../components/GroupedList";
import { SelectPopover } from "../../../components/SelectPopover";
import { useStatusNotification } from "../../../components/StatusNotificationCenter";
import type { ModelSettingsPage } from "../../modelConfiguration/models/modelSettingsTypes";
import { ModelSettingsEditor } from "../../modelConfiguration/models/ModelSettingsEditor";
import { type DefaultModelUsage } from "../../modelConfiguration/models/modelSettingsTypes";

import { useModelsSettings } from "../../modelConfiguration/models/useModelsSettings";
import { useProviderSettings } from "../../modelConfiguration/providers/useProviderSettings";
import { invalidateConnectionTestRequest } from "../../modelConfiguration/probes/settingsConnectionRequests";
import { settingsPath } from "../../../app/settingsRoutes";
import type { ModelCatalog } from "../../modelConfiguration/modelCatalog";
import type { Dispatch, SetStateAction } from "react";
import { SettingsSectionLayout } from "../SettingsSectionLayout";
import { useSettingsNavigation, type SettingsSession } from "../SettingsNavigationContext";
const modelSettingsPageTitles: Record<Exclude<ModelSettingsPage, "root">, string> = {
  thinking: navigationLabels.thinking,
  inputOutput: navigationLabels.inputOutput
};

export function ModelsSettingsSection({ session, modelCatalog, onModelsChanged, refreshModels }: {
  session: SettingsSession; modelCatalog: ModelCatalog; onModelsChanged: Dispatch<SetStateAction<ModelCatalog>>; refreshModels: (isRelevant?: () => boolean) => Promise<void>;
}) {
  const { accountId, composing, isCurrentScope, serialTasks } = session;
  const { location, navigateSettings, actions: { activeSection, detailOpen, selectedProviderId, selectProvider, selectProvidersRoot } } = useSettingsNavigation();
  const {
    providers,
    connectionTestStates,
    setConnectionTestStates,
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
    loaded: providersLoaded,
  } = useProviderSettings({
    accountId,
    composing,
    selectedProviderId,
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
    loadError: modelsLoadError,
  } = useModelsSettings({
    modelCatalog,
    onModelsChanged,
    refreshModels,
    isCurrentScope,
    selectedProvider,
    selectedDraft,
    autoSaveProviderDraft,
    setTestStates,
  });
  const defaultSaveSequences = useRef<Record<string, number>>({});
  const { updateDefaultModel } = createDefaultModelActions({
    defaultSaveSequences, addedModels,
    setModelDefaults: next => { if (isCurrentScope()) onModelsChanged(current => ({ ...current, defaults: typeof next === "function" ? next(current.defaults) : next })); },
    serialTasks, isCurrentScope
  });
  const selectedProviderModels = selectedProvider
    ? addedModels.filter(
      (model) => model.provider_id === selectedProvider.provider_id,
    )
    : [];

  const navigationPath = settingsPath(location);
  useEffect(() => {
    setModelPickerOpen(false);
    setRemoteModels([]);
    setModelPickerError("");
    if (location.section === "providers" && !location.providerId) {
      for (const id of providerConnectionTestRequestsRef.current.keys()) invalidateConnectionTestRequest(providerConnectionTestRequestsRef, id);
      setConnectionTestStates({});
    }
  }, [navigationPath]);

  const providerConnectionStates = connectionTestStates;
  const defaultModelOptions = addedModels;
  const modelsLoading = modelCatalog.status === "loading";
  const loadError = providerLoadError || modelsLoadError;
  const editingModelId = location.section === "providers" ? location.modelId ?? "" : "";
  const editingModelPage = location.section === "providers" ? location.page : "root";
  const setEditingModelPage = (page: ModelSettingsPage) => navigateSettings({ section: "providers", providerId: selectedProviderId, modelId: editingModelId, page });
  const editingModel = selectedProviderModels.find(
    (model) => model.model_id === editingModelId
  ) ?? null;
  function unavailableDefaultLabel(modelId: string) {
    const model = addedModels.find(item => item.model_id === modelId);
    return model && !isModelAvailable(model) ? <span className="model-provider-label"><span>{model.model_name}</span><ModelServiceStatus model={model} /></span> : undefined;
  }

  function defaultModelOptionsForUsage(usage: DefaultModelUsage) {
    return defaultModelOptions.filter((model) => eligibleForDefault(model, usage));
  }

  function openModelSettings(modelId: string) {
    navigateSettings({ section: "providers", providerId: selectedProviderId, modelId, page: "root" });
  }

  function goBackFromModelSettings() {
    if (editingModelPage !== "root") {
      setEditingModelPage("root");
      return;
    }
    selectProvider(selectedProviderId);
  }

  const [customDialog, setCustomDialog] = useState<ProviderSummary | "new" | null>(null);
  useStatusNotification(loadError, { id: "settings-load-error", title: "设置加载失败", tone: "error" });
  useStatusNotification(selectedProviderFeedback?.status === "error" ? selectedProviderFeedback.message : "", { id: "settings-provider-status", title: "模型设置未完成", tone: "error" });
  if (activeSection !== "providers" && activeSection !== "defaults") return null;
  const title = editingModel ? (editingModelPage === "root" ? editingModel.model_name : modelSettingsPageTitles[editingModelPage])
    : activeSection === "defaults" ? navigationLabels.defaults : selectedProvider?.provider_name ?? navigationLabels.providers;
  return <>
    {customDialog ? <CustomProviderDialog provider={customDialog === "new" ? undefined : customDialog} onClose={() => setCustomDialog(null)} onSaved={selectProvider} /> : null}
    <SettingsSectionLayout title={title} toolbarTitle={activeSection === "providers" && !detailOpen ? navigationLabels.providers : title}
      onBack={editingModelId ? goBackFromModelSettings : undefined} wide
      secondaryList={activeSection === "providers" ? <ProviderList providers={providers} providerConnectionStates={connectionTestStates}
        selectedProviderId={selectedProviderId} detailOpen={detailOpen} selectProvider={selectProvider} onCreate={() => setCustomDialog("new")} /> : undefined}>
      {selectedProviderId && !selectedProvider ? <EmptyState layout="inline"
        title={loadError ? "模型提供方读取失败" : !providersLoaded ? "正在读取模型提供方…" : "模型提供方不存在或已删除"}
        description={loadError || undefined} /> : editingModelId && !editingModel ? <EmptyState layout="inline"
          title={loadError ? "模型读取失败" : modelsLoading ? "正在读取模型…" : "模型不存在或已删除"}
          description={loadError || undefined} /> : editingModel ? (
            <ModelSettingsEditor
              key={editingModel.model_id}
              model={editingModel}
              onDelete={async () => {
                const deleted = await deleteAddedModel(editingModel.model_id);
                if (deleted) {
                  selectProvider(selectedProviderId);
                }
                return deleted;
              }}
              onNavigate={setEditingModelPage}
              onProbe={() => probeAddedModel(editingModel.model_id)}
              onSave={(patch) => updateAddedModel(
                editingModel.model_id,
                patch,
                { notify: false }
              )}
              providerAttachmentMimeTypes={
                selectedProvider?.native_attachment_mime_types ?? []
              }
              page={editingModelPage}
              probing={probingModelIds.includes(editingModel.model_id)}
              supplierFallbackName={selectedProvider?.provider_name ?? "provider"}
              saving={savingModelIds.includes(editingModel.model_id)}
            />
          ) : null}
      {!editingModelId ? <div className="settings-detail-column">
        {activeSection === "providers" && selectedProvider?.provider_kind === "managed" ? <SerenitaProviderPanel>
          <AddedModelList providerId={selectedProviderId} models={selectedProviderModels} probingModelIds={probingModelIds}
            onOpen={openModelSettings} onDelete={deleteAddedModel} onAdd={() => { void openAddModelModal(); }} />
        </SerenitaProviderPanel> : null}
        {activeSection === "providers" && selectedProvider?.provider_kind !== "managed" ? (
          selectedProvider && selectedDraft ? <ProviderDetail key={selectedProviderId}
            selectedProvider={selectedProvider} selectedDraft={selectedDraft} providerConnectionStates={providerConnectionStates}
            selectedProviderModels={selectedProviderModels} probingModelIds={probingModelIds} setCustomDialog={setCustomDialog}
            selectProvidersRoot={selectProvidersRoot} revealModelCredential={revealModelCredential} updateDraft={updateDraft}
            testProviderConnection={testProviderConnection} openModelSettings={openModelSettings} deleteAddedModel={deleteAddedModel}
            openAddModelModal={openAddModelModal} /> : null
        ) : null}

        {activeSection === "defaults" ? (
          <section className="settings-section default-model-section">
            {[{ title: "生成模型", embedding: false }, { title: "向量模型", embedding: true }].map(group => <div className="model-settings-block" key={group.title}>
              <h3>{group.title}</h3>
              <GroupedList layout="fields" className="default-model-list" density="standard">
                {defaultModelItems.filter(item => item.key.endsWith("embedding") === group.embedding).map((item) => (
                  <div className="default-model-row field-row" key={item.key}>
                    <span className="field-label">{item.label}</span>
                    <SelectPopover
                      ariaLabel={`设置${item.label}`}
                      triggerContent={unavailableDefaultLabel(item.selectedModelId)}
                      menuWidth="content" menuAlign="end" interactionOwner="row"
                      onChange={(modelId) => updateDefaultModel(item.key, modelId)}
                      options={[
                        { label: "不设置", value: "" },
                        ...defaultModelOptionsForUsage(item.key).map((model) => ({
                          label: item.key === "multimodal_embedding" ? `${model.model_name} · ${supportedEmbeddingModalities(model).map(key => modalityLabels[key]).join("、")}` : model.model_name,
                          secondaryLabel: model.provider_name,
                          value: model.model_id
                        }))
                      ]}
                      value={item.selectedModelId}
                    />
                  </div>
                ))}
              </GroupedList>
              {group.embedding ? <p className="content-description">记忆模块选用文本向量模型</p> : <p className="content-description">长期记忆生成模型优先关闭思考；无法关闭时，固定使用模型支持的最低思考档位。</p>}
            </div>)}
          </section>
        ) : null}

      </div> : null}
    </SettingsSectionLayout>
    {modelPickerOpen && selectedProvider ? <ModelPickerDialog key={selectedProviderId} selectedProvider={selectedProvider}
      remoteModels={remoteModels} addedModels={addedModels} addingRemoteModelIds={addingRemoteModelIds}
      modelPickerLoading={modelPickerLoading} modelPickerError={modelPickerError} retryLoadRemoteModels={retryLoadRemoteModels}
      setModelPickerOpen={setModelPickerOpen} addRemoteModel={addRemoteModel} deleteAddedModel={deleteAddedModel} /> : null}
  </>;
}
