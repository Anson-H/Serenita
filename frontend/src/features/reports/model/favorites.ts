/** 执行医疗报告收藏与取消收藏，同步账号收藏列表和操作反馈。 */
import {
  type Dispatch,
  type SetStateAction
} from "react";
import {
  apiClient,
  type Favorite,
  type ReportDetail
} from "../../../api/client";

type Dependencies = {
  memberId: string;
  favoritingReport: boolean;
  favoritedReportIds: Set<string>;
  setActionError: Dispatch<SetStateAction<string>>;
  setActionMessage: Dispatch<SetStateAction<string>>;
  setFavoritingReport: Dispatch<SetStateAction<boolean>>;
  isCurrentScope: () => boolean;
  setFavorites: Dispatch<SetStateAction<Favorite[]>>;
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
      setActionMessage(uniqueReportIds.length === 1 ? "医疗报告已收藏。" : "所选医疗报告已收藏。");
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
            error: error instanceof Error ? error.message : "医疗报告收藏失败。",
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
            ? failedOutcomes[0]?.error ?? "医疗报告收藏失败。"
            : `有 ${failedOutcomes.length} 份医疗报告未能收藏，请重试。`
        );
      } else {
        setActionMessage(
          uniqueReportIds.length === 1
            ? "医疗报告已收藏。"
            : `已收藏 ${uniqueReportIds.length} 份医疗报告。`
        );
      }
      return failedReportIds;
    } finally {
      setFavoritingReport(false);
    }
  }

  async function toggleReportFavorite() {
    if (!memberId || !selectedReportId || !selectedReport || favoritingReport) return false;
    setFavoritingReport(true);
    try {
      if (reportFavorite) {
        await apiClient.deleteFavorite(reportFavorite.favorite_id);
        if (!isCurrentScope()) return false;
        setFavorites(current => current.filter(item => item.favorite_id !== reportFavorite.favorite_id));
      } else {
        const favorite = await apiClient.createFavoriteSource({ memberId, sourceType: "report", sourceId: selectedReportId, tags: [] });
        if (!isCurrentScope()) return false;
        setFavorites(current => [...current.filter(item => item.favorite_id !== favorite.favorite_id), favorite]);
      }
      return true;
    } catch (error) {
      if (!isCurrentScope()) return false;
      setActionError(error instanceof Error ? error.message : "医疗报告收藏失败。");
      return false;
    } finally {
      setFavoritingReport(false);
    }
  }
  return {
    favoriteReports,
    toggleReportFavorite
  };
}
