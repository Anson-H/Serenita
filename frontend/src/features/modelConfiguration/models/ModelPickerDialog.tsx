import { useRef, useState, useMemo } from "react";
import { createPortal } from "react-dom";
import type { AddedModel, RemoteModel, ProviderSummary } from "../../../api/models/modelTypes";
import { useModalDialog } from "../../../components/useModalDialog";
import { groupRemoteModelsBySupplier } from "./remoteModelPresentation";
import { RemoteModelPicker } from "./RemoteModelPicker";
export function ModelPickerDialog({ selectedProvider, remoteModels, addedModels, addingRemoteModelIds, modelPickerLoading, modelPickerError, retryLoadRemoteModels, setModelPickerOpen, addRemoteModel, deleteAddedModel }: {
  selectedProvider: ProviderSummary; remoteModels: RemoteModel[]; addedModels: AddedModel[]; addingRemoteModelIds: string[];
  modelPickerLoading: boolean; modelPickerError: string; retryLoadRemoteModels: () => void | Promise<void>; setModelPickerOpen: (open: boolean) => void;
  addRemoteModel: (model: RemoteModel) => void | Promise<void>; deleteAddedModel: (id: string) => boolean | Promise<boolean>;
}) {
  const selectedProviderId = selectedProvider.provider_id;
  const [modelPickerQuery, setModelPickerQuery] = useState("");
  const [removingModelIds, setRemovingModelIds] = useState<string[]>([]);
  const modelPickerDialogRef = useRef<HTMLElement | null>(null);
  const [expandedModelSupplierGroups, setExpandedModelSupplierGroups] = useState<Set<string>>(
    () => new Set()
  );
  const [expandedSearchModelSupplierGroups, setExpandedSearchModelSupplierGroups] = useState<Set<string>>(
    () => new Set()
  );
  useModalDialog({
    active: true,
    dialogRef: modelPickerDialogRef,
    onEscape: () => {
      setModelPickerQuery("");
      setModelPickerOpen(false);
    }
  });
  const normalizedModelPickerQuery = modelPickerQuery.trim().toLocaleLowerCase("zh-CN");
  const visibleRemoteModels = normalizedModelPickerQuery
    ? remoteModels.filter((model) =>
      `${model.remote_model_id} ${model.model_name}`.toLocaleLowerCase("zh-CN")
        .includes(normalizedModelPickerQuery)
    )
    : remoteModels;
  const currentProviderGroupName = selectedProvider?.provider_name ?? "提供方";
  const visibleRemoteModelGroups = useMemo(
    () => groupRemoteModelsBySupplier(visibleRemoteModels, currentProviderGroupName),
    [currentProviderGroupName, visibleRemoteModels]
  );
  async function toggleRemoteModel(model: RemoteModel, addedModel?: AddedModel) {
    if (!addedModel) {
      await addRemoteModel(model);
      return;
    }
    if (removingModelIds.includes(addedModel.model_id)) return;
    setRemovingModelIds((current) => [...new Set([...current, addedModel.model_id])]);
    try {
      await deleteAddedModel(addedModel.model_id);
    } finally {
      setRemovingModelIds((current) => current.filter((id) => id !== addedModel.model_id));
    }
  }

  return createPortal(
    <RemoteModelPicker
      modelPickerDialogRef={modelPickerDialogRef}
      setModelPickerQuery={setModelPickerQuery}
      setModelPickerOpen={setModelPickerOpen}
      modelPickerLoading={modelPickerLoading}
      modelPickerError={modelPickerError}
      retryLoadRemoteModels={retryLoadRemoteModels}
      normalizedModelPickerQuery={normalizedModelPickerQuery}
      setExpandedSearchModelSupplierGroups={setExpandedSearchModelSupplierGroups}
      modelPickerQuery={modelPickerQuery}
      visibleRemoteModels={visibleRemoteModels}
      visibleRemoteModelGroups={visibleRemoteModelGroups}
      expandedSearchModelSupplierGroups={expandedSearchModelSupplierGroups}
      expandedModelSupplierGroups={expandedModelSupplierGroups}
      setExpandedModelSupplierGroups={setExpandedModelSupplierGroups}
      addedModels={addedModels}
      selectedProviderId={selectedProviderId}
      addingRemoteModelIds={addingRemoteModelIds}
      removingModelIds={removingModelIds}
      toggleRemoteModel={toggleRemoteModel}
      remoteModels={remoteModels}
      catalogOnly={selectedProvider.provider_kind === "managed"}
    />,
    document.body
  );
}
