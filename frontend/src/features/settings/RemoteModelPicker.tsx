import type { Dispatch, RefObject, SetStateAction } from "react";
import type {
  AddedModel,
  RemoteModel
} from "../../api/client";
import { GroupedList } from "../../components/GroupedList";
import {
  CheckIcon,
  ChevronDownIcon,
  XIcon
} from "../../components/icons";
import type { RemoteModelSupplierGroup } from "./remoteModelPresentation";
import { remoteModelIdentity } from "./remoteModelPresentation";

type Props = {
  modelPickerDialogRef: RefObject<HTMLElement | null>;
  setModelPickerQuery: Dispatch<SetStateAction<string>>;
  setModelPickerOpen: (open: boolean) => void;
  modelPickerLoading: boolean;
  modelPickerError: string;
  normalizedModelPickerQuery: string;
  setExpandedSearchModelSupplierGroups: Dispatch<SetStateAction<Set<string>>>;
  modelPickerQuery: string;
  visibleRemoteModels: RemoteModel[];
  visibleRemoteModelGroups: RemoteModelSupplierGroup[];
  expandedSearchModelSupplierGroups: Set<string>;
  expandedModelSupplierGroups: Set<string>;
  setExpandedModelSupplierGroups: Dispatch<SetStateAction<Set<string>>>;
  addedModels: AddedModel[];
  selectedProviderId: string;
  addingRemoteModelIds: string[];
  removingModelIds: string[];
  toggleRemoteModel: (model: RemoteModel, addedModel?: AddedModel) => Promise<void>;
  remoteModels: RemoteModel[];
};

export function RemoteModelPicker({
  modelPickerDialogRef,
  setModelPickerQuery,
  setModelPickerOpen,
  modelPickerLoading,
  modelPickerError,
  normalizedModelPickerQuery,
  setExpandedSearchModelSupplierGroups,
  modelPickerQuery,
  visibleRemoteModels,
  visibleRemoteModelGroups,
  expandedSearchModelSupplierGroups,
  expandedModelSupplierGroups,
  setExpandedModelSupplierGroups,
  addedModels,
  selectedProviderId,
  addingRemoteModelIds,
  removingModelIds,
  toggleRemoteModel,
  remoteModels
}: Props) {
  return (<div className="model-picker-backdrop dialog-viewport-backdrop">
    <section aria-labelledby="model-picker-title" aria-modal="true" className="model-picker-modal dialog-viewport-surface dialog-title-ellipsis" ref={modelPickerDialogRef} role="dialog" tabIndex={-1}>
      <header className="dialog-titlebar model-picker-header">
        <h2 data-modal-initial-focus id="model-picker-title" tabIndex={-1}>添加模型</h2>
        <button
          aria-label="关闭添加模型"
          className="control control--titlebar control--icon control--ghost icon-action-control secondary-button settings-icon-button titlebar-icon-control"
          onClick={() => {
            setModelPickerQuery("");
            setModelPickerOpen(false);
          }}
          title="关闭添加模型"
          type="button"
        >
          <XIcon />
        </button>
      </header>
      <div className="dialog-body model-picker-body">
        <input
          aria-label="搜索可添加模型"
          className="model-picker-search"
          disabled={modelPickerLoading || Boolean(modelPickerError)}
          onChange={(event) => {
            const nextQuery = event.target.value;
            if (Boolean(normalizedModelPickerQuery) !== Boolean(nextQuery.trim())) {
              setExpandedSearchModelSupplierGroups(new Set());
            }
            setModelPickerQuery(nextQuery);
          }}
          placeholder="搜索模型 ID"
          type="search"
          value={modelPickerQuery}
        />
        {modelPickerLoading ? <p className="status-message testing">加载中...</p> : null}
        {!modelPickerLoading && !modelPickerError && visibleRemoteModels.length ? (
          <div
            aria-label="可添加模型"
            className="model-list model-picker-list root-disclosure-stack scroll-content"
          >
            {visibleRemoteModelGroups.map((group) => {
              const collapsed = normalizedModelPickerQuery
                ? !expandedSearchModelSupplierGroups.has(group.key)
                : !expandedModelSupplierGroups.has(group.key);
              return (
                <section
                  className="model-picker-group root-disclosure-list"
                  key={group.key}
                >
                  <button
                    aria-expanded={!collapsed}
                    className="model-picker-group-toggle root-disclosure-toggle"
                    onClick={() => {
                      if (normalizedModelPickerQuery) {
                        setExpandedSearchModelSupplierGroups((current) => {
                          const next = new Set(current);
                          if (next.has(group.key)) next.delete(group.key);
                          else next.add(group.key);
                          return next;
                        });
                      } else {
                        setExpandedModelSupplierGroups((current) => {
                          const next = new Set(current);
                          if (next.has(group.key)) next.delete(group.key);
                          else next.add(group.key);
                          return next;
                        });
                      }
                    }}
                    type="button"
                  >
                    <ChevronDownIcon className={collapsed ? "collapsed" : ""} />
                    <span>{group.label}</span>
                    <small>{group.models.length}</small>
                  </button>
                  {!collapsed ? <GroupedList className="root-disclosure-content" selectionMode="multiple" density="standard">{group.models.map((model) => {
                    const identity = remoteModelIdentity(model.remote_model_id);
                    const added = addedModels.find(
                      (item) =>
                        item.provider_id === selectedProviderId &&
                        item.remote_model_id === model.remote_model_id
                    );
                    const adding = addingRemoteModelIds.includes(model.remote_model_id);
                    const removing = Boolean(added && removingModelIds.includes(added.model_id));
                    return (
                      <button
                        aria-label={added
                          ? removing
                            ? `正在取消添加模型：${model.remote_model_id}`
                            : `取消添加模型：${model.remote_model_id}`
                          : adding
                            ? `正在添加模型：${model.remote_model_id}`
                            : `添加模型：${model.remote_model_id}`}
                        aria-pressed={Boolean(added)}
                        className="model-row model-picker-model-row"
                        disabled={adding || removing}
                        key={model.remote_model_id}
                        onClick={() => void toggleRemoteModel(model, added)}
                        title={added
                          ? removing ? "正在取消添加" : "取消添加"
                          : adding ? "正在添加" : "添加模型"}
                        type="button"
                      >
                        <span
                          aria-hidden="true"
                          className="model-picker-selection-indicator selection-check-control"
                          data-selected={added ? "true" : undefined}
                        >
                          {added ? (
                            <CheckIcon className="model-picker-selection-check selection-check-icon" />
                          ) : null}
                        </span>
                        <div className="model-picker-row-copy">
                          <span title={model.remote_model_id}>{identity.model}</span>
                        </div>
                      </button>
                    );
                  })}</GroupedList> : null}
                </section>
              );
            })}
          </div>
        ) : null}
        {!modelPickerLoading && !modelPickerError && !visibleRemoteModels.length ? (
          <p className="status-message">
            {remoteModels.length ? "没有匹配的模型。" : "暂无可添加模型。"}
          </p>
        ) : null}
        {!modelPickerLoading && !modelPickerError ? (
          <p className="object-list-count">共 {visibleRemoteModels.length} 个模型</p>
        ) : null}
      </div>
    </section>
  </div>);
}
