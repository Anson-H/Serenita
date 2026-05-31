import { type RefObject, useLayoutEffect } from "react";

type UseFavoriteListAlignmentOptions = {
  active: boolean;
  favoriteDetailId: string | null;
  favoriteListPanelRef: RefObject<HTMLElement | null>;
  favoriteListRef: RefObject<HTMLDivElement | null>;
  favoriteSelectionMode: boolean;
  favoritesLength: number;
};

export function useFavoriteListAlignment({
  active,
  favoriteDetailId,
  favoriteListPanelRef,
  favoriteListRef,
  favoriteSelectionMode,
  favoritesLength
}: UseFavoriteListAlignmentOptions) {
  useLayoutEffect(() => {
    if (!active) {
      return;
    }

    const panel = favoriteListPanelRef.current;
    const list = favoriteListRef.current;
    if (!panel || !list) {
      return;
    }

    let frameHandle: number | null = null;
    const scheduleFavoriteListAlignment = () => {
      if (frameHandle !== null) {
        return;
      }
      frameHandle = window.requestAnimationFrame(() => {
        frameHandle = null;
        updateFavoriteListAlignment();
      });
    };

    const observer = typeof ResizeObserver === "undefined"
      ? null
      : new ResizeObserver(scheduleFavoriteListAlignment);
    observer?.observe(panel);
    observer?.observe(list);
    window.addEventListener("resize", scheduleFavoriteListAlignment);
    scheduleFavoriteListAlignment();

    return () => {
      if (frameHandle !== null) {
        window.cancelAnimationFrame(frameHandle);
      }
      observer?.disconnect();
      window.removeEventListener("resize", scheduleFavoriteListAlignment);
    };
  }, [active, favoriteDetailId, favoriteListPanelRef, favoriteListRef, favoriteSelectionMode, favoritesLength]);

  function updateFavoriteListAlignment() {
    const panel = favoriteListPanelRef.current;
    const list = favoriteListRef.current;
    if (!panel || !list) {
      return;
    }

    const listStyle = window.getComputedStyle(list);
    const listHorizontalBorderWidth =
      Number.parseFloat(listStyle.borderLeftWidth) + Number.parseFloat(listStyle.borderRightWidth);
    const actualScrollbarGutter = Math.max(
      0,
      list.offsetWidth - list.clientWidth - listHorizontalBorderWidth
    );
    const listInlineEndPadding =
      Number.parseFloat(listStyle.getPropertyValue("padding-inline-end") || listStyle.paddingRight) || 0;
    panel.style.setProperty(
      "--favorite-list-end-compensation",
      `${Math.ceil(actualScrollbarGutter + listInlineEndPadding)}px`
    );
  }
}
