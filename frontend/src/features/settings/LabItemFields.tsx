import { navigationLabels } from "../../components/navigationLabels";
import { GroupedList } from "../../components/GroupedList";
import { TrashIcon } from "../../components/icons";
import {
  syncCommittedText
} from "../../utils/inputMethod";
import { AliasEditor } from "./LabDictionaryDialogs";
import type { ItemDraft, LabDictionaryDetailPage } from "./labDictionaryDrafts";
import {
  SettingsListForwardIcon,
  SettingsLongTextField,
  SettingsTrailingSummary
} from "./SettingsPrimitives";

type Props = {
  saving: boolean;
  flushScheduledItemSave: () => void;
  scheduleItemDraft: (update: (current: ItemDraft) => ItemDraft, { immediate }?: { immediate?: boolean; }) => void;
  itemForm: ItemDraft;
  selectedId: string;
  primaryCategorySummary: string;
  onNavigate: (page: LabDictionaryDetailPage) => void;
  relatedCategorySummary: string;
  requestDelete: (ids?: string[]) => Promise<void>;
};

export function LabItemFields({
  saving,
  flushScheduledItemSave,
  scheduleItemDraft,
  itemForm,
  selectedId,
  primaryCategorySummary,
  onNavigate,
  relatedCategorySummary,
  requestDelete
}: Props) {
  return (<section aria-busy={saving ? "true" : "false"} className="dictionary-editor-form">
    <GroupedList layout="fields" density="standard">
      <label className="field-row">规范名称<input aria-required="true" maxLength={128} onBlur={flushScheduledItemSave} onChange={(event) => scheduleItemDraft((current) => ({ ...current, item_name_zh: event.target.value }))} onCompositionEnd={(event) => syncCommittedText(event, (item_name_zh) => scheduleItemDraft((current) => ({ ...current, item_name_zh })))} value={itemForm.item_name_zh} /></label>
      <label className="field-row">别名<AliasEditor aliases={itemForm.aliases} key={selectedId} onChange={(aliases) => scheduleItemDraft((current) => ({ ...current, aliases }), { immediate: true })} /></label>
    </GroupedList>
    <div className="dictionary-category-navigation">
      <h2>所属分类</h2>
      <GroupedList layout="navigation" className="dictionary-category-navigation-list" density="standard">
        <button
          aria-label={`主分类，当前为${primaryCategorySummary}`}
          className="grouped-labeled-navigation-row"
          onClick={() => onNavigate("primary-category")}
          type="button"
        >
          <span>{navigationLabels.primaryCategory}</span>
          <small className="dictionary-category-navigation-summary" title={primaryCategorySummary}>
            {primaryCategorySummary}
          </small>
          <SettingsListForwardIcon />
        </button>
        <button
          className="grouped-labeled-navigation-row grouped-list-wrapping-navigation-row"
          aria-label={`关联分类，当前为${relatedCategorySummary}`}
          onClick={() => onNavigate("related-categories")}
          type="button"
        >
          <span>{navigationLabels.relatedCategories}</span>
          <SettingsTrailingSummary className="dictionary-category-navigation-summary" title={relatedCategorySummary}>
            {relatedCategorySummary}
          </SettingsTrailingSummary>
          <SettingsListForwardIcon />
        </button>
      </GroupedList>
    </div>
    <GroupedList layout="fields" density="standard">
      <SettingsLongTextField label="说明" onBlur={flushScheduledItemSave} onChange={(event) => scheduleItemDraft((current) => ({ ...current, description: event.target.value }))} onCompositionEnd={(event) => syncCommittedText(event, (description) => scheduleItemDraft((current) => ({ ...current, description })))} placeholder="备注" value={itemForm.description} />
    </GroupedList>
    <footer className="dictionary-editor-actions">
      <button aria-label="删除指标" className="control control--secondary control--danger destructive-action-button removal-action-control" disabled={saving} onClick={() => void requestDelete()} type="button">
        <TrashIcon className="message-action-icon" />
        <span>删除指标</span>
      </button>
    </footer>
  </section>);
}
