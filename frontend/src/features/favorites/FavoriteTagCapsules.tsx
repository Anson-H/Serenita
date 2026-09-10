import { navigationLabels } from "../../components/navigationLabels";
import {ContentDialog} from "../../components/ContentDialog";
import { useId } from "react";
import {
  CheckIcon,
  EditIcon,
  PlusIcon,
  XIcon
} from "../../components/icons";
import {
  formTextValue,
  isImeComposing,
  syncCommittedText
} from "../../utils/inputMethod";

type FavoriteTagCapsulesProps = {
  adding: boolean;
  containerRef?: (node: HTMLDivElement | null) => void;
  draft: string;
  editing: boolean;
  favoriteId: string;
  onCommitAdd: (value: string) => void;
  onDraftChange: (value: string) => void;
  onRemoveTag: (tag: string) => void;
  onStartAdd: () => void;
  onToggleEdit: () => void;
  tags: string[];
  title: string;
};

export function FavoriteTagCapsules({
  adding,
  containerRef,
  draft,
  editing,
  favoriteId,
  onCommitAdd,
  onDraftChange,
  onRemoveTag,
  onStartAdd,
  onToggleEdit,
  tags,
  title
}: FavoriteTagCapsulesProps) {

  const formId=useId();

  return (
    <div
      className="favorite-tag-capsules metadata-token-editor"
      data-editing={editing ? "true" : undefined}
      data-favorite-id={favoriteId}
      onClick={(event) => event.stopPropagation()}
      ref={containerRef}
    >
      {tags.length ? (
        tags.map((tag) => (
          <span
            className="favorite-tag-pill metadata-token"
            data-removable={editing ? "true" : undefined}
            key={`${favoriteId}-${tag}`}
          >
            <span className="metadata-token-label">{tag}</span>
            {editing ? (
              <button
                aria-label={`删除标签：${tag}`}
                className="control control--inline-compact control--icon control--ghost control--danger favorite-tag-remove-button metadata-token-remove-button removal-action-control"
                data-interaction-owner="self"
                onClick={() => onRemoveTag(tag)}
                title="删除标签"
                type="button"
              >
                <XIcon />
              </button>
            ) : null}
          </span>
        ))
      ) : (
        <span className="favorite-tag-pill-empty metadata-token-empty">未设置标签</span>
      )}
      {editing && adding ? (
        <ContentDialog creation title={navigationLabels.addTag} onClose={()=>onCommitAdd('')} actions={<><button className="control control--primary" type="submit" form={formId} disabled={!draft.trim()}><CheckIcon/>完成</button></>}><form id={formId}
          className="favorite-tag-add-form metadata-token-add-form"
          onSubmit={(event) => {
            event.preventDefault();
            onCommitAdd(formTextValue(event.currentTarget, "favorite-tag", draft));
          }}
        >
          <input
            aria-label={`添加标签：${title}`}
            name="favorite-tag"
            onChange={(event) => onDraftChange(event.target.value)}
            onCompositionEnd={(event) => syncCommittedText(event, onDraftChange)}
            onKeyDown={(event) => {
              if (event.key === "Enter" && isImeComposing(event)) {
                event.preventDefault();
              }
            }}
            placeholder="新标签"
            value={draft}
          />
        </form></ContentDialog>
      ) : null}
      {editing && !adding ? (
        <button
          aria-label={`添加标签：${title}`}
          className="control control--inline-compact control--icon control--ghost favorite-tag-add-button metadata-token-add-button metadata-token-action-button"
          data-interaction-owner="self"
          onClick={onStartAdd}
          type="button"
        >
          <PlusIcon />
        </button>
      ) : null}
      <button
        aria-label={`编辑标签：${title}`}
        className="control control--inline-compact control--icon control--ghost favorite-tag-edit-button metadata-token-action-button"
        data-active={editing ? "true" : undefined}
        data-interaction-owner="self"
        onClick={onToggleEdit}
        title={editing ? "完成编辑" : "编辑标签"}
        type="button"
      >
        <EditIcon />
      </button>
    </div>
  );
}
