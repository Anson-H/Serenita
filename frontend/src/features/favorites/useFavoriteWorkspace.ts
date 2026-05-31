import { useEffect, useRef, useState } from "react";

import { Favorite, apiClient } from "../../api/client";
import {
  addFavoriteIds,
  applyLocalFavoriteTagsToDetail,
  applyLocalFavoriteTagsToList,
  applySavedFavoriteDetail,
  applySavedFavoriteList,
  favoriteTagsForState,
  normalizedFavoriteTags,
  removeDeletedFavoriteDetail,
  removeFavoriteIds,
  toggleFavoriteId
} from "./favoriteState";

type UseFavoriteWorkspaceOptions = {
  setComposerError: (value: string) => void;
};

export function useFavoriteWorkspace({ setComposerError }: UseFavoriteWorkspaceOptions) {
  const [favorites, setFavorites] = useState<Favorite[]>([]);
  const [favoriteSelectionMode, setFavoriteSelectionMode] = useState(false);
  const [selectedFavoriteIds, setSelectedFavoriteIds] = useState<string[]>([]);
  const [favoriteDetail, setFavoriteDetail] = useState<Favorite | null>(null);
  const [editingFavoriteTagIds, setEditingFavoriteTagIds] = useState<string[]>([]);
  const [editingFavoriteDetailTagId, setEditingFavoriteDetailTagId] = useState<string | null>(null);
  const [addingFavoriteTagId, setAddingFavoriteTagId] = useState<string | null>(null);
  const [favoriteTagInput, setFavoriteTagInput] = useState("");
  const pendingFavoriteTagsRef = useRef(new Map<string, string[]>());
  const favoriteDetailAutoSaveRef = useRef<HTMLDivElement | null>(null);
  const favoriteListPanelRef = useRef<HTMLElement | null>(null);
  const favoriteListRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const favoriteIds = new Set(favorites.map((favorite) => favorite.favorite_id));
    setSelectedFavoriteIds((current) => current.filter((favoriteId) => favoriteIds.has(favoriteId)));
    setEditingFavoriteTagIds((current) => current.filter((favoriteId) => favoriteIds.has(favoriteId)));
    setEditingFavoriteDetailTagId((current) => (current && !favoriteIds.has(current) ? null : current));
    setFavoriteDetail((current) => (current && !favoriteIds.has(current.favorite_id) ? null : current));
    if (addingFavoriteTagId && !favoriteIds.has(addingFavoriteTagId)) {
      setAddingFavoriteTagId(null);
      setFavoriteTagInput("");
    }
  }, [addingFavoriteTagId, favorites]);

  useEffect(() => {
    if (
      !editingFavoriteTagIds.length &&
      !editingFavoriteDetailTagId &&
      !addingFavoriteTagId &&
      pendingFavoriteTagsRef.current.size === 0
    ) {
      return;
    }

    function handleFavoriteTagOutsidePointerDown(event: PointerEvent) {
      const target = event.target;
      if (!(target instanceof Element)) {
        return;
      }
      if (favoriteDetailAutoSaveRef.current?.contains(target)) {
        return;
      }
      if (target.closest('.favorite-tag-capsules[data-editing="true"]')) {
        return;
      }
      if (addingFavoriteTagId && favoriteTagInput.trim()) {
        appendFavoriteTag(addingFavoriteTagId, favoriteTagInput);
      } else if (addingFavoriteTagId) {
        setAddingFavoriteTagId(null);
        setFavoriteTagInput("");
      }
      setEditingFavoriteTagIds([]);
      setEditingFavoriteDetailTagId(null);
      void flushFavoriteDetailTags();
      void flushAllFavoriteTags();
    }

    document.addEventListener("pointerdown", handleFavoriteTagOutsidePointerDown);
    return () => document.removeEventListener("pointerdown", handleFavoriteTagOutsidePointerDown);
  }, [addingFavoriteTagId, editingFavoriteDetailTagId, editingFavoriteTagIds, favoriteTagInput]);

  async function showFavorite(favoriteId: string) {
    const detail = await apiClient.getFavorite(favoriteId);
    setFavoriteDetail(detail);
  }

  function closeFavoriteDetail() {
    const detailId = favoriteDetail?.favorite_id;
    if (detailId && addingFavoriteTagId === detailId && favoriteTagInput.trim()) {
      updateFavoriteTagsLocally(detailId, [...favoriteTagsFor(detailId), favoriteTagInput]);
    }
    if (detailId) {
      void flushFavoriteTags(detailId);
    }
    if (detailId && addingFavoriteTagId === detailId) {
      setAddingFavoriteTagId(null);
      setFavoriteTagInput("");
    }
    setEditingFavoriteDetailTagId(null);
    setFavoriteDetail(null);
  }

  function favoriteTagsFor(favoriteId: string) {
    return favoriteTagsForState(favorites, favoriteDetail, favoriteId);
  }

  async function saveFavoriteTags(favoriteId: string, tags: string[]) {
    const normalizedTags = normalizedFavoriteTags(tags);
    const updated = await apiClient.updateFavorite(favoriteId, normalizedTags);
    setFavoriteDetail((current) => applySavedFavoriteDetail(current, favoriteId, updated));
    setFavorites((current) => applySavedFavoriteList(current, favoriteId, updated));
    return updated;
  }

  function updateFavoriteTagsLocally(favoriteId: string, tags: string[]) {
    const normalizedTags = normalizedFavoriteTags(tags);
    pendingFavoriteTagsRef.current.set(favoriteId, normalizedTags);
    setFavoriteDetail((current) => applyLocalFavoriteTagsToDetail(current, favoriteId, normalizedTags));
    setFavorites((current) => applyLocalFavoriteTagsToList(current, favoriteId, normalizedTags));
  }

  async function flushFavoriteTags(favoriteId: string) {
    const pendingTags = pendingFavoriteTagsRef.current.get(favoriteId);
    if (!pendingTags) {
      return;
    }
    pendingFavoriteTagsRef.current.delete(favoriteId);
    try {
      await saveFavoriteTags(favoriteId, pendingTags);
    } catch (error) {
      setComposerError(error instanceof Error ? error.message : "标签保存失败，请稍后重试。");
    }
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

  function toggleFavoriteSelection(favoriteId: string) {
    setSelectedFavoriteIds((current) => toggleFavoriteId(current, favoriteId));
  }

  function toggleFavoriteSelectionMode() {
    const nextSelectionMode = !favoriteSelectionMode;
    setFavoriteSelectionMode(nextSelectionMode);
    if (!nextSelectionMode) {
      setSelectedFavoriteIds([]);
      setEditingFavoriteTagIds([]);
      setEditingFavoriteDetailTagId(null);
      setAddingFavoriteTagId(null);
      setFavoriteTagInput("");
      void flushAllFavoriteTags();
    }
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
      setEditingFavoriteDetailTagId(favoriteId);
    } else {
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

  function commitFavoriteTagDraft() {
    if (!addingFavoriteTagId) {
      return;
    }
    appendFavoriteTag(addingFavoriteTagId, favoriteTagInput);
  }

  function removeFavoriteTag(favoriteId: string, tagToRemove: string) {
    updateFavoriteTagsLocally(
      favoriteId,
      favoriteTagsFor(favoriteId).filter((tag) => tag !== tagToRemove)
    );
  }

  async function batchDeleteFavorites() {
    if (!selectedFavoriteIds.length) {
      return;
    }
    const result = await apiClient.batchDeleteFavorites(selectedFavoriteIds);
    const deletedFavoriteIds = new Set(result.deleted_ids);
    setSelectedFavoriteIds([]);
    setFavoriteSelectionMode(false);
    setEditingFavoriteTagIds((current) => removeFavoriteIds(current, deletedFavoriteIds));
    setEditingFavoriteDetailTagId((current) => (current && deletedFavoriteIds.has(current) ? null : current));
    setFavoriteDetail((current) => removeDeletedFavoriteDetail(current, deletedFavoriteIds));
    const response = await apiClient.fetchFavorites();
    setFavorites(response.favorites);
    if (result.failed.length) {
      setComposerError(`有 ${result.failed.length} 条收藏未能取消，请刷新后重试。`);
    }
  }

  function resetFavoriteWorkspaceState() {
    pendingFavoriteTagsRef.current.clear();
    setFavorites([]);
    setFavoriteSelectionMode(false);
    setSelectedFavoriteIds([]);
    setFavoriteDetail(null);
    setEditingFavoriteTagIds([]);
    setEditingFavoriteDetailTagId(null);
    setAddingFavoriteTagId(null);
    setFavoriteTagInput("");
  }

  return {
    addingFavoriteTagId,
    beginBatchTagEditing,
    beginFavoriteTagAdd,
    batchDeleteFavorites,
    closeFavoriteDetail,
    commitFavoriteTagDraft,
    editingFavoriteDetailTagId,
    editingFavoriteTagIds,
    favoriteDetail,
    favoriteDetailAutoSaveRef,
    favoriteListPanelRef,
    favoriteListRef,
    favoriteSelectionMode,
    favoriteTagInput,
    favorites,
    flushAllFavoriteTags,
    removeFavoriteTag,
    resetFavoriteWorkspaceState,
    selectedFavoriteIds,
    setFavoriteTagInput,
    setFavorites,
    setSelectedFavoriteIds,
    showFavorite,
    toggleFavoriteSelection,
    toggleFavoriteSelectionMode,
    toggleFavoriteTagEditor
  };
}

export type FavoriteWorkspaceState = ReturnType<typeof useFavoriteWorkspace>;
