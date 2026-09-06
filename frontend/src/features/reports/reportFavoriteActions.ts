import type * as React from "react";
import {
  type Dispatch,
  type SetStateAction
} from "react";
import {
  apiClient,
  type Favorite,
  type ReportDetail
} from "../../api/client";

type Dependencies = {
  memberId: string;
  favoritingReport: boolean;
  favoritedReportIds: Set<string>;
  setActionError: Dispatch<SetStateAction<string>>;
  setActionMessage: Dispatch<SetStateAction<string>>;
  setFavoritingReport: Dispatch<SetStateAction<boolean>>;
  isCurrentScope: () => boolean;
  setFavorites: Dispatch<SetStateAction<Favorite[]>>;
  detailRequestSequenceRef: React.RefObject<number>;
  selectedReportId: string | null;
  selectedReport: ReportDetail | null;
  reportFavorite: Favorite | null;
};

export function createReportFavoriteActions({
  memberId,
  favoritingReport,
  favoritedReportIds,
  setActionError,
  setActionMessage,
  setFavoritingReport,
  isCurrentScope,
  setFavorites,
  detailRequestSequenceRef,
  selectedReportId,
  selectedReport,
  reportFavorite
}: Dependencies) {
  async function favoriteReports(reportIds: string[]) {
    const uniqueReportIds = [...new Set(reportIds.filter(Boolean))];
    if (!memberId || !uniqueReportIds.length || favoritingReport) return uniqueReportIds;
    const pendingReportIds = uniqueReportIds.filter(
      (reportId) => !favoritedReportIds.has(reportId)
    );
    if (!pendingReportIds.length) {
      setActionError("");
      setActionMessage(uniqueReportIds.length === 1 ? "报告已收藏。" : "所选报告已收藏。");
      return [];
    }

    setFavoritingReport(true);
    setActionError("");
    setActionMessage("");
    try {
      const outcomes = await Promise.all(pendingReportIds.map(async (reportId) => {
        try {
          const favorite = await apiClient.createFavoriteSource({
            memberId,
            sourceType: "report",
            sourceId: reportId,
            tags: []
          });
          return { favorite, reportId, success: true as const };
        } catch (error) {
          return {
            error: error instanceof Error ? error.message : "报告收藏失败。",
            reportId,
            success: false as const
          };
        }
      }));
      if (!isCurrentScope()) return uniqueReportIds;
      const createdFavorites = outcomes
        .filter((outcome) => outcome.success)
        .map((outcome) => outcome.favorite);
      const failedOutcomes = outcomes.filter((outcome) => !outcome.success);
      const failedReportIds = failedOutcomes.map((outcome) => outcome.reportId);

      if (createdFavorites.length) {
        setFavorites((current) => {
          const byId = new Map(current.map((favorite) => [favorite.favorite_id, favorite]));
          createdFavorites.forEach((favorite) => byId.set(favorite.favorite_id, favorite));
          return [...byId.values()];
        });
      }

      if (failedOutcomes.length) {
        setActionError(
          pendingReportIds.length === 1
            ? failedOutcomes[0]?.error ?? "报告收藏失败。"
            : `有 ${failedOutcomes.length} 份报告未能收藏，请重试。`
        );
      } else {
        setActionMessage(
          uniqueReportIds.length === 1
            ? "报告已收藏。"
            : `已收藏 ${uniqueReportIds.length} 份报告。`
        );
      }
      return failedReportIds;
    } finally {
      setFavoritingReport(false);
    }
  }

  async function toggleReportFavorite() {
    const sequence = detailRequestSequenceRef.current;
    const operationIsCurrent = () => isCurrentScope() && sequence === detailRequestSequenceRef.current;
    if (!memberId || !selectedReportId || !selectedReport || favoritingReport) return false;
    setFavoritingReport(true);
    try {
      if (reportFavorite) await apiClient.deleteFavorite(reportFavorite.favorite_id);
      else await apiClient.createFavoriteSource({ memberId, sourceType: "report", sourceId: selectedReportId, tags: [] });
      if (!operationIsCurrent()) return false;
      const favoritesResponse = await apiClient.fetchFavorites();
      if (!operationIsCurrent()) return false;
      setFavorites(favoritesResponse.favorites);
      if (!operationIsCurrent()) return false;
      return true;
    } catch (error) {
      if (!operationIsCurrent()) return false;
      setActionError(error instanceof Error ? error.message : "报告收藏失败。");
      return false;
    } finally {
      if (operationIsCurrent()) {
        setFavoritingReport(false);
      }
    }
  }
  return {
    favoriteReports,
    toggleReportFavorite
  };
}
