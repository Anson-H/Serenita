import type { ReactNode } from "react";

import { FavoritesWorkspace } from "./FavoritesWorkspace";
import type { FavoriteWorkspaceState } from "./useFavoriteWorkspace";

type FavoritesWorkspacePanelProps = {
  favoriteWorkspace: FavoriteWorkspaceState;
  onOpenConversation: (sessionId: string, sourceMessageId: string) => void | Promise<void>;
  onOpenReport: (reportId: string, memberId: string) => void | Promise<void>;
  sidebarToggle: ReactNode;
};

export function FavoritesWorkspacePanel({
  favoriteWorkspace,
  onOpenConversation,
  onOpenReport,
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
      favorites={favoriteWorkspace.favorites}
      favoriteSelectionMode={favoriteWorkspace.favoriteSelectionMode}
      favoriteTagInput={favoriteWorkspace.favoriteTagInput}
      onOpenConversation={(sessionId, sourceMessageId) => void onOpenConversation(sessionId, sourceMessageId)}
      onOpenReport={(reportId, memberId) => void onOpenReport(reportId, memberId)}
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
