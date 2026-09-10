import type * as React from "react";
import { Favorite, apiClient } from "../../api/client";
import { showStatusNotification } from "../../components/StatusNotificationCenter";
import {
  addFavoriteIds,
  applyLocalFavoriteTagsToDetail,
  applyLocalFavoriteTagsToList,
  applySavedFavoriteDetail,
  applySavedFavoriteList,
  favoriteTagsForState,
  normalizedFavoriteTags
} from "./favoriteState";
import { sameFavoriteTags } from './favoriteTagEquality';

type Dependencies = {
  getFavorite?: (id: string) => Favorite | undefined;
  favorites: Favorite[];
  favoriteDetail: Favorite | null;
  pendingFavoriteTagsRef: React.RefObject<Map<string, string[]>>;
  setFavoriteDetail: React.Dispatch<React.SetStateAction<Favorite | null>>;
  setFavorites: React.Dispatch<React.SetStateAction<Favorite[]>>;
  favoriteTagSavePromisesRef: React.RefObject<Map<string, Promise<void>>>;
  favoriteWorkspaceRevisionRef: React.RefObject<number>;
  selectedFavoriteIds: string[];
  setComposerError: (value: string) => void;
  setEditingFavoriteTagIds: React.Dispatch<React.SetStateAction<string[]>>;
  editingFavoriteDetailTagId: string | null;
  setEditingFavoriteDetailTagId: React.Dispatch<React.SetStateAction<string | null>>;
  addingFavoriteTagId: string | null;
  setAddingFavoriteTagId: React.Dispatch<React.SetStateAction<string | null>>;
  setFavoriteTagInput: React.Dispatch<React.SetStateAction<string>>;
  editingFavoriteTagIds: string[];
  favoriteTagInput: string;
};

export function createFavoriteTagActions({
  getFavorite,
  favorites,
  favoriteDetail,
  pendingFavoriteTagsRef,
  setFavoriteDetail,
  setFavorites,
  favoriteTagSavePromisesRef,
  favoriteWorkspaceRevisionRef,
  selectedFavoriteIds,
  setComposerError,
  setEditingFavoriteTagIds,
  editingFavoriteDetailTagId,
  setEditingFavoriteDetailTagId,
  addingFavoriteTagId,
  setAddingFavoriteTagId,
  setFavoriteTagInput,
  editingFavoriteTagIds,
  favoriteTagInput
}: Dependencies) {
  function favoriteTagsFor(favoriteId: string) {
    return pendingFavoriteTagsRef.current.get(favoriteId) ?? getFavorite?.(favoriteId)?.tags ?? favoriteTagsForState(favorites, favoriteDetail, favoriteId);
  }

  function updateFavoriteTagsLocally(favoriteId: string, tags: string[]) {
    const normalizedTags = normalizedFavoriteTags(tags);
    pendingFavoriteTagsRef.current.set(favoriteId, normalizedTags);
    setFavoriteDetail((current) => applyLocalFavoriteTagsToDetail(current, favoriteId, normalizedTags));
    setFavorites((current) => applyLocalFavoriteTagsToList(current, favoriteId, normalizedTags));
  }

  function flushFavoriteTags(favoriteId: string) {
    const activeSave = favoriteTagSavePromisesRef.current.get(favoriteId);
    if (activeSave) return activeSave;
    const workspaceRevision = favoriteWorkspaceRevisionRef.current;
    let savePromise: Promise<void>;
    savePromise = (async () => {
      while (workspaceRevision === favoriteWorkspaceRevisionRef.current) {
        const pendingTags = pendingFavoriteTagsRef.current.get(favoriteId);
        if (!pendingTags) return;
        try {
          const updated = await apiClient.updateFavorite(favoriteId, pendingTags);
          if (workspaceRevision !== favoriteWorkspaceRevisionRef.current) return;
          const latestTags = pendingFavoriteTagsRef.current.get(favoriteId);
          if (!latestTags) return;
          if (!sameFavoriteTags(latestTags, pendingTags)) continue;
          pendingFavoriteTagsRef.current.delete(favoriteId);
          setFavoriteDetail((current) => applySavedFavoriteDetail(current, favoriteId, updated));
          setFavorites((current) => applySavedFavoriteList(current, favoriteId, updated));
          showStatusNotification({
            id: `favorite-tags-${favoriteId}`,
            message: "收藏标签已保存。",
            tone: "success"
          });
          return;
        } catch (error) {
          if (
            workspaceRevision !== favoriteWorkspaceRevisionRef.current ||
            !pendingFavoriteTagsRef.current.has(favoriteId)
          ) return;
          const message = error instanceof Error && error.message
            ? error.message
            : "标签保存失败，请稍后重试。";
          showStatusNotification({
            action: {
              label: "重试",
              onClick: () => { void flushFavoriteTags(favoriteId); }
            },
            durationMs: null,
            id: `favorite-tags-${favoriteId}`,
            message: `收藏标签未保存。${message}`,
            tone: "error"
          });
          return;
        }
      }
    })().finally(() => {
      if (favoriteTagSavePromisesRef.current.get(favoriteId) === savePromise) {
        favoriteTagSavePromisesRef.current.delete(favoriteId);
      }
    });
    favoriteTagSavePromisesRef.current.set(favoriteId, savePromise);
    return savePromise;
  }

  async function flushFavoriteDetailTags() {
    if (!favoriteDetail) {
      return;
    }
    await flushFavoriteTags(favoriteDetail.favorite_id);
  }

  async function flushAllFavoriteTags() {
    const pendingFavoriteIds = Array.from(pendingFavoriteTagsRef.current.keys());
    await Promise.all(pendingFavoriteIds.map((favoriteId) => flushFavoriteTags(favoriteId)));
  }

  function beginBatchTagEditing() {
    if (!selectedFavoriteIds.length) {
      setComposerError("请先选择要设置标签的收藏。");
      return;
    }
    setEditingFavoriteTagIds((current) => addFavoriteIds(current, selectedFavoriteIds));
  }

  function toggleFavoriteTagEditor(favoriteId: string, surface: "list" | "detail") {
    if (surface === "detail") {
      const currentlyEditingDetail = editingFavoriteDetailTagId === favoriteId;
      setEditingFavoriteDetailTagId(currentlyEditingDetail ? null : favoriteId);
      if (currentlyEditingDetail) {
        if (addingFavoriteTagId === favoriteId) {
          setAddingFavoriteTagId(null);
          setFavoriteTagInput("");
        }
        void flushFavoriteTags(favoriteId);
      }
      return;
    }

    const currentlyEditing = editingFavoriteTagIds.includes(favoriteId);
    setEditingFavoriteTagIds((current) =>
      currentlyEditing
        ? current.filter((editingFavoriteId) => editingFavoriteId !== favoriteId)
        : [...current, favoriteId]
    );
    if (currentlyEditing) {
      if (addingFavoriteTagId === favoriteId) {
        setAddingFavoriteTagId(null);
        setFavoriteTagInput("");
      }
      void flushFavoriteTags(favoriteId);
    }
  }

  function beginFavoriteTagAdd(favoriteId: string, surface: "list" | "detail") {
    if (surface === "detail") {
      setEditingFavoriteTagIds(current=>current.filter(id=>id!==favoriteId));
      setEditingFavoriteDetailTagId(favoriteId);
    } else {
      setEditingFavoriteDetailTagId(current=>current===favoriteId?null:current);
      setEditingFavoriteTagIds((current) => (current.includes(favoriteId) ? current : [...current, favoriteId]));
    }
    setAddingFavoriteTagId(favoriteId);
    setFavoriteTagInput("");
  }

  function appendFavoriteTag(favoriteId: string, tag: string) {
    const trimmedTag = tag.trim();
    setAddingFavoriteTagId(null);
    setFavoriteTagInput("");
    if (!trimmedTag) {
      return;
    }
    updateFavoriteTagsLocally(favoriteId, [...favoriteTagsFor(favoriteId), trimmedTag]);
  }

  function commitFavoriteTagDraft(submittedTag = favoriteTagInput) {
    if (!addingFavoriteTagId) {
      return;
    }
    appendFavoriteTag(addingFavoriteTagId, submittedTag);
    if(submittedTag.trim())void flushFavoriteTags(addingFavoriteTagId);
  }

  function removeFavoriteTag(favoriteId: string, tagToRemove: string) {
    updateFavoriteTagsLocally(
      favoriteId,
      favoriteTagsFor(favoriteId).filter((tag) => tag !== tagToRemove)
    );
  }
  return {
    favoriteTagsFor,
    updateFavoriteTagsLocally,
    flushFavoriteTags,
    flushFavoriteDetailTags,
    flushAllFavoriteTags,
    beginBatchTagEditing,
    toggleFavoriteTagEditor,
    beginFavoriteTagAdd,
    appendFavoriteTag,
    commitFavoriteTagDraft,
    removeFavoriteTag
  };
}
