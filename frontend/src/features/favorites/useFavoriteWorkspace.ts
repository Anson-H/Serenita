import { useEffect, useRef, useState } from "react";
import { Favorite, apiClient } from "../../api/client";
import { showStatusNotification } from "../../components/StatusNotificationCenter";
import {
  removeDeletedFavoriteDetail,
  removeFavoriteIds,
  toggleFavoriteId
} from "./favoriteState";
import { createFavoriteTagActions } from './favoriteTagActions';

type UseFavoriteWorkspaceOptions = {
  setComposerError: (value: string) => void;
  memberCollection?: object;
};

export function useFavoriteWorkspace({ setComposerError, memberCollection }: UseFavoriteWorkspaceOptions) {
  const [favorites, setFavorites] = useState<Favorite[]>([]);
  const [favoriteSelectionMode, setFavoriteSelectionMode] = useState(false);
  const [selectedFavoriteIds, setSelectedFavoriteIds] = useState<string[]>([]);
  const [favoriteDetail, setFavoriteDetail] = useState<Favorite | null>(null);
  const [editingFavoriteTagIds, setEditingFavoriteTagIds] = useState<string[]>([]);
  const [editingFavoriteDetailTagId, setEditingFavoriteDetailTagId] = useState<string | null>(null);
  const [addingFavoriteTagId, setAddingFavoriteTagId] = useState<string | null>(null);
  const [favoriteTagInput, setFavoriteTagInput] = useState("");
  const pendingFavoriteTagsRef = useRef(new Map<string, string[]>());
  const favoriteTagSavePromisesRef = useRef(new Map<string, Promise<void>>());
  const favoriteWorkspaceRevisionRef = useRef(0);
  const favoriteDetailRequestSequenceRef = useRef(0);
  const favoriteDetailRequestTargetRef = useRef<string | null>(null);
  const favoriteDetailAutoSaveRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!memberCollection) return;
    let disposed = false;
    void apiClient.fetchFavorites().then(response => {
      if (disposed) return;
      const identities = new Map(response.favorites.map(item => [item.favorite_id, item]));
      setFavorites(current => current.map(item => {
        const updated = identities.get(item.favorite_id);
        return updated ? { ...item, member_id: updated.member_id, member_name: updated.member_name } : item;
      }));
    }).catch(() => undefined);
    if (favoriteDetail?.favorite_id) {
      void apiClient.getFavorite(favoriteDetail.favorite_id).then(updated => {
        if (!disposed) setFavoriteDetail(current => current?.favorite_id === updated.favorite_id
          ? { ...current, member_id: updated.member_id, member_name: updated.member_name, source_available: updated.source_available }
          : current);
      }).catch(() => undefined);
    }
    return () => { disposed = true; };
  }, [memberCollection, favoriteDetail?.favorite_id]);

  useEffect(() => {
    const favoriteIds = new Set(favorites.map((favorite) => favorite.favorite_id));
    setSelectedFavoriteIds((current) => current.filter((favoriteId) => favoriteIds.has(favoriteId)));
    setEditingFavoriteTagIds((current) => current.filter((favoriteId) => favoriteIds.has(favoriteId)));
    setEditingFavoriteDetailTagId((current) => (current && !favoriteIds.has(current) ? null : current));
    setFavoriteDetail((current) => (current && !favoriteIds.has(current.favorite_id) ? null : current));
    for (const favoriteId of pendingFavoriteTagsRef.current.keys()) {
      if (!favoriteIds.has(favoriteId)) pendingFavoriteTagsRef.current.delete(favoriteId);
    }
    if (
      favoriteDetailRequestTargetRef.current &&
      !favoriteIds.has(favoriteDetailRequestTargetRef.current)
    ) {
      favoriteDetailRequestSequenceRef.current += 1;
      favoriteDetailRequestTargetRef.current = null;
    }
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
      const visibleTagInput = document.querySelector<HTMLInputElement>(
        '.favorite-tag-add-form input[name="favorite-tag"]'
      );
      const submittedTag = visibleTagInput?.value ?? favoriteTagInput;
      if (addingFavoriteTagId && submittedTag.trim()) {
        appendFavoriteTag(addingFavoriteTagId, submittedTag);
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
    const requestSequence = ++favoriteDetailRequestSequenceRef.current;
    favoriteDetailRequestTargetRef.current = favoriteId;
    try {
      const detail = await apiClient.getFavorite(favoriteId);
      if (requestSequence !== favoriteDetailRequestSequenceRef.current) return;
      setFavoriteDetail(detail);
    } catch (error) {
      if (requestSequence !== favoriteDetailRequestSequenceRef.current) return;
      favoriteDetailRequestTargetRef.current = null;
      setComposerError(error instanceof Error ? error.message : "收藏详情加载失败。");
    }
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
    favoriteDetailRequestSequenceRef.current += 1;
    favoriteDetailRequestTargetRef.current = null;
    setFavoriteDetail(null);
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

  async function batchDeleteFavorites() {
    if (!selectedFavoriteIds.length) {
      return;
    }
    try {
      const result = await apiClient.batchDeleteFavorites(selectedFavoriteIds);
      const deletedFavoriteIds = new Set(result.deleted_ids);
      for (const favoriteId of deletedFavoriteIds) {
        pendingFavoriteTagsRef.current.delete(favoriteId);
      }
      if (
        favoriteDetailRequestTargetRef.current &&
        deletedFavoriteIds.has(favoriteDetailRequestTargetRef.current)
      ) {
        favoriteDetailRequestSequenceRef.current += 1;
        favoriteDetailRequestTargetRef.current = null;
      }
      setSelectedFavoriteIds([]);
      setFavoriteSelectionMode(false);
      setEditingFavoriteTagIds((current) => removeFavoriteIds(current, deletedFavoriteIds));
      setEditingFavoriteDetailTagId((current) => (current && deletedFavoriteIds.has(current) ? null : current));
      setFavoriteDetail((current) => removeDeletedFavoriteDetail(current, deletedFavoriteIds));
      const response = await apiClient.fetchFavorites();
      setFavorites(response.favorites);
      if (result.failed.length) {
        setComposerError(`有 ${result.failed.length} 条收藏未能取消，请刷新后重试。`);
      } else {
        showStatusNotification({
          id: "favorite-batch-delete-success",
          message: "所选收藏已取消。",
          tone: "success"
        });
      }
    } catch (error) {
      setComposerError(error instanceof Error ? error.message : "取消收藏失败。");
    }
  }

  function resetFavoriteWorkspaceState() {
    favoriteWorkspaceRevisionRef.current += 1;
    favoriteDetailRequestSequenceRef.current += 1;
    favoriteDetailRequestTargetRef.current = null;
    pendingFavoriteTagsRef.current.clear();
    favoriteTagSavePromisesRef.current.clear();
    setFavorites([]);
    setFavoriteSelectionMode(false);
    setSelectedFavoriteIds([]);
    setFavoriteDetail(null);
    setEditingFavoriteTagIds([]);
    setEditingFavoriteDetailTagId(null);
    setAddingFavoriteTagId(null);
    setFavoriteTagInput("");
  }
  const {
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
  } = createFavoriteTagActions({
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
  });

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
