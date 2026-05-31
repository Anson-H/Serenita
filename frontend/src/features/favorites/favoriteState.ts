import type { Favorite } from "../../api/client";
import { normalizeFavoriteTags } from "./favoriteTags";

export function favoriteTagsForState(
  favorites: Favorite[],
  favoriteDetail: Favorite | null,
  favoriteId: string
) {
  if (favoriteDetail?.favorite_id === favoriteId) {
    return favoriteDetail.tags;
  }
  return favorites.find((favorite) => favorite.favorite_id === favoriteId)?.tags ?? [];
}

export function mergeUpdatedFavorite(favorite: Favorite, updated: Favorite) {
  return {
    ...favorite,
    content_summary: updated.content_summary,
    source_available: updated.source_available ?? favorite.source_available,
    tags: updated.tags,
    title: updated.title,
    updated_at: updated.updated_at
  };
}

export function applySavedFavoriteDetail(
  current: Favorite | null,
  favoriteId: string,
  updated: Favorite
) {
  return current?.favorite_id === favoriteId ? { ...current, ...updated } : current;
}

export function applySavedFavoriteList(
  favorites: Favorite[],
  favoriteId: string,
  updated: Favorite
) {
  return favorites.map((favorite) =>
    favorite.favorite_id === favoriteId ? mergeUpdatedFavorite(favorite, updated) : favorite
  );
}

export function normalizedFavoriteTags(tags: string[]) {
  return normalizeFavoriteTags(tags);
}

export function applyLocalFavoriteTagsToDetail(
  current: Favorite | null,
  favoriteId: string,
  tags: string[]
) {
  return current?.favorite_id === favoriteId ? { ...current, tags } : current;
}

export function applyLocalFavoriteTagsToList(
  favorites: Favorite[],
  favoriteId: string,
  tags: string[]
) {
  return favorites.map((favorite) =>
    favorite.favorite_id === favoriteId ? { ...favorite, tags } : favorite
  );
}

export function toggleFavoriteId(current: string[], favoriteId: string) {
  return current.includes(favoriteId)
    ? current.filter((currentFavoriteId) => currentFavoriteId !== favoriteId)
    : [...current, favoriteId];
}

export function addFavoriteIds(current: string[], favoriteIds: string[]) {
  return Array.from(new Set([...current, ...favoriteIds]));
}

export function removeFavoriteIds(current: string[], favoriteIds: Set<string>) {
  return current.filter((favoriteId) => !favoriteIds.has(favoriteId));
}

export function removeDeletedFavoriteDetail(
  current: Favorite | null,
  deletedFavoriteIds: Set<string>
) {
  return current && deletedFavoriteIds.has(current.favorite_id) ? null : current;
}
