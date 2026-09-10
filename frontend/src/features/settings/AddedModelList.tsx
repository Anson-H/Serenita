import type { AddedModel } from "../../api/client";
import { EmptyState } from "../../components/EmptyState";
import { GroupedList } from "../../components/GroupedList";
import { ListCount } from "../../components/ListCount";
import { PlusIcon } from "../../components/icons";
import { navigationLabels } from "../../components/navigationLabels";
import { useListDeleteActions } from "../../components/useListDeleteActions";
import { useActiveScope } from "../../utils/useActiveScope";
import { modelTypeLabels } from "../modelConfiguration/modelEligibility";
import { AddedModelCapabilityIcons } from "./ModelCapabilitySummary";
import { SettingsListForwardIcon } from "./SettingsPrimitives";

export function AddedModelList({ providerId, models, probingModelIds, onAdd, onOpen, onDelete }: {
  providerId: string;
  models: AddedModel[];
  probingModelIds: string[];
  onAdd: () => void;
  onOpen: (id: string) => void;
  onDelete: (id: string) => boolean | Promise<boolean>;
}) {
  const scope = `added-models:${providerId}`;
  const isCurrent = useActiveScope(scope);
  const actions = useListDeleteActions({
    scope, enabled: true, label: "模型", countLabel: "个模型",
    entries: models.map(model => ({ id: model.model_id, name: model.remote_model_id })),
    onDelete: async ids => {
      const failed: string[] = [];
      for (const id of ids) {
        if (!isCurrent()) { failed.push(id); continue; }
        try { if (!await onDelete(id)) failed.push(id); }
        catch { failed.push(id); }
      }
      return failed;
    }
  });
  return <section className={`provider-model-section${models.length ? "" : " empty"}`} aria-label="模型列表" onKeyDown={actions.onKeyDown}>
    <div className="provider-model-content">
      <div className="model-section-header"><h2>已添加模型</h2></div>
      <div className="added-model-list-area">
        {actions.heading}
        <GroupedList className="model-list added-model-list" density="standard" selectionMode={actions.selectionMode ? "multiple" : undefined}>
          {!actions.selectionMode ? <div className="model-item add-model-item" data-grouped-list-item>
            <button aria-label={navigationLabels.addModel} className="control control--row add-model-button grouped-list-create-button" data-interaction-owner="row" onClick={onAdd} disabled={actions.busy} type="button">
              <PlusIcon className="settings-action-icon" /><span>{navigationLabels.addModel}</span>
            </button>
          </div> : null}
          {models.map(model => <div className="model-item" data-grouped-list-item key={model.model_id}>
            <button {...actions.rowProps(model.model_id)}
              aria-label={actions.selectionMode ? `${actions.selected(model.model_id) ? "取消选择" : "选择"}模型：${model.remote_model_id}` : `打开模型详情：${model.remote_model_id}`}
              aria-haspopup={!actions.selectionMode ? "menu" : undefined}
              role={actions.selectionMode ? "checkbox" : undefined}
              aria-checked={actions.selectionMode ? actions.selected(model.model_id) : undefined}
              className={`model-row model-detail-row${actions.selectionMode ? " selection-mode" : ""}`}
              data-interaction-owner="row" disabled={actions.busy}
              onClick={() => actions.selectionMode ? actions.toggle(model.model_id) : onOpen(model.model_id)} type="button">
              {actions.indicator(model.model_id)}
              <span className="model-row-name" title={model.remote_model_id}>{model.remote_model_id}</span>
              <span className="model-row-actions">
                <AddedModelCapabilityIcons model={model} />
                <span className="control-row-description model-type-label">{probingModelIds.includes(model.model_id) ? "检测中" : modelTypeLabels[model.model_type]}</span>
                {!actions.selectionMode ? <SettingsListForwardIcon className="model-row-chevron" /> : null}
              </span>
            </button>
          </div>)}
        </GroupedList>
        {actions.toolbar}
      </div>
      {!models.length ? <EmptyState title="暂未添加模型" /> : null}
    </div>
    {models.length ? <ListCount total={models.length} unit="个" label="模型" /> : null}
    {actions.portal}
  </section>;
}
