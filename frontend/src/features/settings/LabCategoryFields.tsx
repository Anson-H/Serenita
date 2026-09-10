import { EmptyState } from "../../components/EmptyState";
import type { LabDictionaryCategory, LabDictionaryItem } from "../../api/client";
import {
  type LabDictionaryResponse
} from "../../api/client";
import { GroupedList } from "../../components/GroupedList";
import { TrashIcon } from "../../components/icons";
import {
  syncCommittedText
} from "../../utils/inputMethod";
import type { CategoryDraft, DictionaryTab } from "./labDictionaryDrafts";
import {
  SettingsListForwardIcon,
  SettingsLongTextField
} from "./SettingsPrimitives";

type Props = {
  saving: boolean;
  flushScheduledCategorySave: () => void;
  scheduleCategoryDraft: (update: (current: CategoryDraft) => CategoryDraft, { immediate }?: { immediate?: boolean; }) => void;
  categoryForm: CategoryDraft;
  activeCategoryItems: LabDictionaryItem[];
  selectEntity: (nextTab: DictionaryTab, id: string, source?: LabDictionaryResponse | null) => void;
  activeCategory: LabDictionaryCategory;
  requestDelete: (ids?: string[]) => Promise<void>;
};

export function LabCategoryFields({
  saving,
  flushScheduledCategorySave,
  scheduleCategoryDraft,
  categoryForm,
  activeCategoryItems,
  selectEntity,
  activeCategory,
  requestDelete
}: Props) {
  return (<section aria-busy={saving ? "true" : "false"} className="dictionary-editor-form">
    <GroupedList layout="fields" density="standard">
      <label className="field-row">分类名称<input maxLength={64} onBlur={flushScheduledCategorySave} onChange={(event) => scheduleCategoryDraft((current) => ({ ...current, category_name: event.target.value }))} onCompositionEnd={(event) => syncCommittedText(event, (category_name) => scheduleCategoryDraft((current) => ({ ...current, category_name })))} required value={categoryForm.category_name} /></label>
      <SettingsLongTextField label="说明" onBlur={flushScheduledCategorySave} onChange={(event) => scheduleCategoryDraft((current) => ({ ...current, description: event.target.value }))} onCompositionEnd={(event) => syncCommittedText(event, (description) => scheduleCategoryDraft((current) => ({ ...current, description })))} placeholder="备注" value={categoryForm.description} />
    </GroupedList>
    <section
      aria-label={activeCategoryItems.length ? undefined : "关联指标"}
      aria-labelledby={activeCategoryItems.length ? "dictionary-category-members-title" : undefined}
      className="dictionary-category-members"
    >
      {activeCategoryItems.length ? (
        <>
          <header>
            <h2 id="dictionary-category-members-title">包含指标</h2>
            <span>{activeCategoryItems.length} 项</span>
          </header>
          <GroupedList className="dictionary-category-member-list" density="standard">
            {activeCategoryItems.map((item) => (
              <button key={item.item_id} onClick={() => selectEntity("items", item.item_id)} type="button">
                <strong>{item.item_name_zh}</strong>
                <SettingsListForwardIcon className="dictionary-member-chevron" />
              </button>
            ))}
          </GroupedList>
        </>
      ) : (
        <EmptyState layout="inline" title="暂无关联指标" />
      )}
    </section>
    <footer className="dictionary-editor-actions">
      <button aria-label="删除分类" className="control control--secondary control--danger destructive-action-button removal-action-control" disabled={saving || Boolean(activeCategory.primary_item_count)} onClick={() => void requestDelete()} title={activeCategory.primary_item_count ? "请先为相关指标更换主分类" : undefined} type="button">
        <TrashIcon className="message-action-icon" />
        <span>删除分类</span>
      </button>
    </footer>
  </section>);
}
