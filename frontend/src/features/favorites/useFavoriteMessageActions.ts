import {
  type Dispatch,
  type SetStateAction,
} from "react";

import {
  type ConversationMessage,
  type Favorite,
  apiClient
} from "../../api/client";
import { showStatusNotification } from "../../components/StatusNotificationCenter";

type FavoriteMessageActionsOptions = {
  currentSessionId: string | null;
  favorites: Favorite[];
  setComposerError: Dispatch<SetStateAction<string>>;
  setFavorites: Dispatch<SetStateAction<Favorite[]>>;
};

export function useFavoriteMessageActions({
  currentSessionId,
  favorites,
  setComposerError,
  setFavorites
}: FavoriteMessageActionsOptions) {
  async function toggleFavorite(message: ConversationMessage) {
    if (!currentSessionId) {
      return;
    }
    const existing = favorites.find((favorite) => favorite.source_id === message.message_id);
    try {
      if (existing) {
        await apiClient.deleteFavorite(existing.favorite_id);
      } else {
        await apiClient.createFavorite(currentSessionId, message.message_id, []);
      }
      const response = await apiClient.fetchFavorites();
      setFavorites(response.favorites);
      showStatusNotification({
        id: `favorite-message-${message.message_id}`,
        message: existing ? "已取消收藏。" : "已收藏。",
        tone: "success"
      });
    } catch (error) {
      setComposerError(error instanceof Error ? error.message : "收藏操作失败。");
    }
  }

  return {
    toggleFavorite
  };
}
