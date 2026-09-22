import { useState } from "react";
import type { AddedModel, ProviderSummary } from "../../../api/models/modelTypes";
import { modelConfigurationChanged } from "../../../api/models/modelServiceApi";
import { EditIcon, TrashIcon, XIcon } from "../../../components/icons";
import { AddedModelList } from "../models/AddedModelList";
import { ProviderConnectionFields } from "./ProviderConnectionFields";
import { ProviderConnectionTest } from "../probes/ProviderConnectionTest";
import { useModelSettingsApi } from "../ModelSettingsApi";
import type { ProviderConnectionTestState } from "../../../utils/requestStatus";
import type { ProviderDraft } from "./providerDraft";
export function ProviderDetail({ selectedProvider, selectedDraft, providerConnectionStates, selectedProviderModels, probingModelIds, setCustomDialog, selectProvidersRoot, revealModelCredential, updateDraft, testProviderConnection, openModelSettings, deleteAddedModel, openAddModelModal }: {
  selectedProvider: ProviderSummary; selectedDraft: ProviderDraft; providerConnectionStates: Record<string, ProviderConnectionTestState>;
  selectedProviderModels: AddedModel[]; probingModelIds: string[]; setCustomDialog: (provider: ProviderSummary) => void; selectProvidersRoot: () => void;
  revealModelCredential: (id: string) => boolean | Promise<boolean>; updateDraft: (id: string, patch: Partial<ProviderDraft>) => void;
  testProviderConnection: (id: string) => void | Promise<void>; openModelSettings: (id: string) => void;
  deleteAddedModel: (id: string) => boolean | Promise<boolean>; openAddModelModal: () => void | Promise<void>;
}) {
  const api = useModelSettingsApi();
  const selectedProviderId = selectedProvider.provider_id;
  const [deleteProviderOpen, setDeleteProviderOpen] = useState(false);
  const [providerActionError, setProviderActionError] = useState("");
  const [deletingProvider, setDeletingProvider] = useState(false);

  return (
    <section className="settings-section provider-panel">
      <div className="provider-workspace">
        {selectedProvider?.provider_kind === "custom" ? <div className="settings-section">
          <div className="serenita-provider-actions"><button className="control control--compact" type="button" onClick={() => setCustomDialog(selectedProvider)}><EditIcon /><span>编辑提供方名称</span></button><button className="control control--compact control--danger" type="button" onClick={() => setDeleteProviderOpen(true)}><TrashIcon /><span>删除自定义提供方</span></button></div>
          {deleteProviderOpen ? <div className="serenita-provider-group" role="group" aria-label="确认删除提供方"><p className="content-description">删除“{selectedProvider.provider_name}”及其已添加模型，历史调用和记忆索引保留。</p><div className="serenita-provider-actions"><button className="control control--compact" type="button" disabled={deletingProvider} onClick={() => setDeleteProviderOpen(false)}><XIcon /><span>取消</span></button><button className="control control--compact control--danger" type="button" disabled={deletingProvider} onClick={() => {
            setDeletingProvider(true); setProviderActionError("");
            void api.deleteCustomProvider(selectedProvider.provider_id).then(() => { setDeleteProviderOpen(false); modelConfigurationChanged(); selectProvidersRoot(); }).catch(error => setProviderActionError(error.message)).finally(() => setDeletingProvider(false));
          }}><TrashIcon /><span>确认删除提供方</span></button></div></div> : null}
          {providerActionError ? <p role="alert">{providerActionError}</p> : null}
        </div> : null}
        {selectedProvider && selectedDraft ? (
          <form
            className="provider-form"
            onSubmit={(event) => {
              event.preventDefault();
            }}
          >
            <ProviderConnectionFields officialUrl={selectedDraft.officialUrl} apiUrl={selectedDraft.apiUrl} apiKey={selectedDraft.apiKey}
              hasApiKey={selectedProvider.has_api_key} onReveal={() => revealModelCredential(selectedProvider.provider_id)}
              onOfficialUrlChange={officialUrl => updateDraft(selectedProvider.provider_id, { officialUrl })}
              onApiUrlChange={apiUrl => updateDraft(selectedProvider.provider_id, { apiUrl })}
              onApiKeyChange={apiKey => updateDraft(selectedProvider.provider_id, { apiKey })} />
            <ProviderConnectionTest key={selectedProvider.provider_id} state={providerConnectionStates[selectedProvider.provider_id]} onTest={() => testProviderConnection(selectedProvider.provider_id)} />
          </form>
        ) : null}
        <AddedModelList
          key={selectedProviderId}
          providerId={selectedProviderId}
          models={selectedProviderModels}
          probingModelIds={probingModelIds}
          onOpen={openModelSettings}
          onDelete={deleteAddedModel}
          onAdd={() => {
            void openAddModelModal();
          }}
        />
      </div>
    </section>
  );
}
