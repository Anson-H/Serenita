import type { LabDictionaryCategory, LabDictionaryItem } from "../../api/client";
import {
  type LabDictionaryResponse
} from "../../api/client";
import { GroupedList } from "../../components/GroupedList";
import { CheckIcon } from "../../components/icons";
import { LabCategoryFields } from './LabCategoryFields';
import type { CategoryDraft, DictionaryTab, ItemDraft, LabDictionaryDetailPage } from "./labDictionaryDrafts";
import { LabItemFields } from './LabItemFields';
import { SettingsDetailPanel } from "./SettingsDetailPanel";
import type { LabCatalog } from "./settingsTypes";

type Props = {
  detailOpen: boolean;
  goBackFromDetail: () => void;
  detailTitle: string;
  dictionary: LabDictionaryResponse | null;
  tab: LabCatalog;
  activeItem: LabDictionaryItem | undefined;
  detailPage: LabDictionaryDetailPage;
  saving: boolean;
  flushScheduledItemSave: () => void;
  scheduleItemDraft: (update: (current: ItemDraft) => ItemDraft, { immediate }?: { immediate?: boolean; }) => void;
  itemForm: ItemDraft;
  selectedId: string;
  primaryCategorySummary: string;
  onNavigate: (page: LabDictionaryDetailPage) => void;
  relatedCategorySummary: string;
  requestDelete: (ids?: string[]) => Promise<void>;
  activeCategory: LabDictionaryCategory | undefined;
  flushScheduledCategorySave: () => void;
  scheduleCategoryDraft: (update: (current: CategoryDraft) => CategoryDraft, { immediate }?: { immediate?: boolean; }) => void;
  categoryForm: CategoryDraft;
  activeCategoryItems: LabDictionaryItem[];
  selectEntity: (nextTab: DictionaryTab, id: string, source?: LabDictionaryResponse | null) => void;
};

export function LabDictionaryDetail({
  detailOpen,
  goBackFromDetail,
  detailTitle,
  dictionary,
  tab,
  activeItem,
  detailPage,
  saving,
  flushScheduledItemSave,
  scheduleItemDraft,
  itemForm,
  selectedId,
  primaryCategorySummary,
  onNavigate,
  relatedCategorySummary,
  requestDelete,
  activeCategory,
  flushScheduledCategorySave,
  scheduleCategoryDraft,
  categoryForm,
  activeCategoryItems,
  selectEntity
}: Props) {
  return (<SettingsDetailPanel
    mobileOpen={detailOpen}
    onBack={goBackFromDetail}
    title={detailTitle}
    wide
  >
    <div className="dictionary-detail-column">
      {dictionary && tab === "items" && activeItem && detailPage === "root" ? (
        <LabItemFields
          saving={saving}
          flushScheduledItemSave={flushScheduledItemSave}
          scheduleItemDraft={scheduleItemDraft}
          itemForm={itemForm}
          selectedId={selectedId}
          primaryCategorySummary={primaryCategorySummary}
          onNavigate={onNavigate}
          relatedCategorySummary={relatedCategorySummary}
          requestDelete={requestDelete}
        />
      ) : null}

      {dictionary && tab === "items" && activeItem && detailPage === "primary-category" ? (
        <div aria-busy={saving ? "true" : "false"} className="dictionary-category-choice-page">
          {dictionary.categories.length ? (
            <GroupedList
              aria-label="主分类"
              className="dictionary-category-choice-list single-choice"
              role="radiogroup"
              density="standard"
            >
              {dictionary.categories.map((category) => {
                const selected = itemForm.primary_category_name === category.category_name;
                return (
                  <button
                    aria-checked={selected}
                    className={selected ? "active" : undefined}
                    key={category.category_name}
                    onClick={() => scheduleItemDraft((current) => ({
                      ...current,
                      primary_category_name: category.category_name,
                      related_category_names: current.related_category_names.filter(
                        (value) => value !== category.category_name
                      )
                    }), { immediate: true })}
                    role="radio"
                    type="button"
                  >
                    <span>{category.category_name}</span>
                  </button>
                );
              })}
            </GroupedList>
          ) : <p className="dictionary-inline-empty">请先在“检验分类目录”创建分类。</p>}
        </div>
      ) : null}

      {dictionary && tab === "items" && activeItem && detailPage === "related-categories" ? (
        <div aria-busy={saving ? "true" : "false"} className="dictionary-category-choice-page">
          {dictionary.categories.some(
            (category) => category.category_name !== itemForm.primary_category_name
          ) ? (
            <GroupedList className="dictionary-category-choice-list" selectionMode="multiple" density="standard">
              {dictionary.categories
                .filter((category) => category.category_name !== itemForm.primary_category_name)
                .map((category) => {
                  const selected = itemForm.related_category_names.includes(category.category_name);
                  return (
                    <button
                      aria-pressed={selected}
                      key={category.category_name}
                      onClick={() => scheduleItemDraft((current) => ({
                        ...current,
                        related_category_names: selected
                          ? current.related_category_names.filter(
                            (value) => value !== category.category_name
                          )
                          : [...current.related_category_names, category.category_name]
                      }), { immediate: true })}
                      type="button"
                    >
                      <span
                        aria-hidden="true"
                        className="dictionary-category-choice-indicator selection-check-control"
                        data-selected={selected ? "true" : undefined}
                      >
                        {selected ? <CheckIcon className="selection-check-icon" /> : null}
                      </span>
                      <span>{category.category_name}</span>
                    </button>
                  );
                })}
            </GroupedList>
          ) : <p className="dictionary-inline-empty">暂无可关联的其他分类。</p>}
        </div>
      ) : null}

      {dictionary && tab === "categories" && activeCategory && detailPage === "root" ? (
        <LabCategoryFields
          saving={saving}
          flushScheduledCategorySave={flushScheduledCategorySave}
          scheduleCategoryDraft={scheduleCategoryDraft}
          categoryForm={categoryForm}
          activeCategoryItems={activeCategoryItems}
          selectEntity={selectEntity}
          activeCategory={activeCategory}
          requestDelete={requestDelete}
        />
      ) : null}
    </div>
  </SettingsDetailPanel>);
}
