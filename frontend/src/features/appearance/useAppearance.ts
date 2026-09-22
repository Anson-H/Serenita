import { useSyncExternalStore } from "react";

export type ThemeMode = "system" | "light" | "dark";
export type ColorStyle = "apricot" | "sage" | "blue" | "mauve" | "oat";
type Appearance = { mode: ThemeMode; style: ColorStyle; theme: "light" | "dark" };

declare global {
  interface Window {
    serenitaAppearance: {
      getSnapshot: () => Appearance;
      subscribe: (listener: () => void) => () => void;
      set: (next: Partial<Pick<Appearance, "mode" | "style">>) => void;
    };
  }
}

export function useAppearance() {
  const store = window.serenitaAppearance;
  return { ...useSyncExternalStore(store.subscribe, store.getSnapshot), setAppearance: store.set };
}
