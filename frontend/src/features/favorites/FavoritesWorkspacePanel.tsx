import type { ReactNode } from "react";

import { FavoritesWorkspace } from "./FavoritesWorkspace";
import type { FavoriteWorkspaceState } from "./useFavoriteWorkspace";

type FavoritesWorkspacePanelProps = {
  favoriteWorkspace: FavoriteWorkspaceState;
  onOpenConversation: (sessionId: string, sourceMessageId: string) => void | Promise<void>;
  sidebarToggle: ReactNode;
};

export function FavoritesWorkspacePanel({
  favoriteWorkspace,
  onOpenConversation,
  sidebarToggle
}: FavoritesWorkspacePanelProps) {
  return (
    <FavoritesWorkspace
      addingFavoriteTagId={favoriteWorkspace.addingFavoriteTagId}
      beginBatchTagEditing={favoriteWorkspace.beginBatchTagEditing}
      beginFavoriteTagAdd={favoriteWorkspace.beginFavoriteTagAdd}
      batchDeleteFavorites={favoriteWorkspace.batchDeleteFavorites}
      closeFavoriteDetail={favoriteWorkspace.closeFavoriteDetail}
      commitFavoriteTagDraft={favoriteWorkspace.commitFavoriteTagDraft}
      editingFavoriteDetailTagId={favoriteWorkspace.editingFavoriteDetailTagId}
      editingFavoriteTagIds={favoriteWorkspace.editingFavoriteTagIds}
      favoriteDetail={favoriteWorkspace.favoriteDetail}
      favoriteDetailAutoSaveRef={favoriteWorkspace.favoriteDetailAutoSaveRef}
      favoriteListPanelRef={favoriteWorkspace.favoriteListPanelRef}
      favoriteListRef={favoriteWorkspace.favoriteListRef}
      favorites={favoriteWorkspace.favorites}
      favoriteSelectionMode={favoriteWorkspace.favoriteSelectionMode}
      favoriteTagInput={favoriteWorkspace.favoriteTagInput}
      onOpenConversation={(sessionId, sourceMessageId) => void onOpenConversation(sessionId, sourceMessageId)}
      removeFavoriteTag={favoriteWorkspace.removeFavoriteTag}
      selectedFavoriteIds={favoriteWorkspace.selectedFavoriteIds}
      setFavoriteTagInput={favoriteWorkspace.setFavoriteTagInput}
      setSelectedFavoriteIds={favoriteWorkspace.setSelectedFavoriteIds}
      showFavorite={favoriteWorkspace.showFavorite}
      sidebarToggle={sidebarToggle}
      toggleFavoriteSelection={favoriteWorkspace.toggleFavoriteSelection}
      toggleFavoriteSelectionMode={favoriteWorkspace.toggleFavoriteSelectionMode}
      toggleFavoriteTagEditor={favoriteWorkspace.toggleFavoriteTagEditor}
    />
  );
}
