import { request } from "./request";
import { type Favorite, type FavoriteSourceType } from "./types";

export function fetchFavorites() {
  return request<{ favorites: Favorite[]; has_more: boolean; next_cursor: string | null }>("/favorites");
}

export function getFavorite(favoriteId: string) {
  return request<Favorite>(`/favorites/${favoriteId}`);
}

export function createFavorite(sourceSessionId: string, sourceId: string, tags: string[]) {
  return createFavoriteSource({
    sourceType: "message",
    sourceSessionId,
    sourceId,
    tags
  });
}

export function createFavoriteSource(input: {
  memberId?: string;
  sourceType: FavoriteSourceType;
  sourceSessionId?: string | null;
  sourceId: string;
  tags: string[];
}) {
  return request<Favorite>("/favorites", {
    method: "POST",
    body: JSON.stringify({
      source_type: input.sourceType,
      member_id: input.memberId,
      ...(input.sourceSessionId ? { source_session_id: input.sourceSessionId } : {}),
      source_id: input.sourceId,
      tags: input.tags
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
