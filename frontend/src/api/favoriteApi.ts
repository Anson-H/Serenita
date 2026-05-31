import { Favorite } from "./types";
import { request } from "./request";

export function fetchFavorites() {
  return request<{ favorites: Favorite[]; has_more: boolean; next_cursor: string | null }>("/favorites");
}

export function getFavorite(favoriteId: string) {
  return request<Favorite>(`/favorites/${favoriteId}`);
}

export function createFavorite(sourceSessionId: string, sourceId: string, tags: string[]) {
  return request<Favorite>("/favorites", {
    method: "POST",
    body: JSON.stringify({
      source_type: "message",
      source_session_id: sourceSessionId,
      source_id: sourceId,
      tags
    })
  });
}

export function updateFavorite(favoriteId: string, tags: string[]) {
  return request<Favorite>(`/favorites/${favoriteId}`, {
    method: "PATCH",
    body: JSON.stringify({ tags })
  });
}

export function deleteFavorite(favoriteId: string) {
  return request<{ success: boolean; favorite_id: string; message: string }>(`/favorites/${favoriteId}`, {
    method: "DELETE"
  });
}

export function batchDeleteFavorites(favoriteIds: string[]) {
  return request<{ success: boolean; deleted_ids: string[]; failed: unknown[] }>("/favorites/batch-delete", {
    method: "POST",
    body: JSON.stringify({ favorite_ids: favoriteIds })
  });
}
