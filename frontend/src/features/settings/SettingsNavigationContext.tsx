import { createContext, useContext, type ReactNode, type RefObject } from "react";
import { createSettingsNavigationActions } from "./settingsNavigationActions";
import type { SettingsLocation } from "../../app/settingsRoutes";
import type { SerialTasks } from "../../utils/serialTasks";
export type SettingsSession = { accountId: string; composing: boolean; isCurrentScope: () => boolean; serialTasks: RefObject<SerialTasks> };
type Navigation = { location: SettingsLocation; navigateSettings: (location: SettingsLocation) => void; actions: ReturnType<typeof createSettingsNavigationActions>; mobileSidebarToggle?: ReactNode };
export const SettingsNavigationContext = createContext<Navigation | null>(null);
export function useSettingsNavigation() {
  const navigation = useContext(SettingsNavigationContext);
  if (!navigation) throw new Error("设置导航尚未装配。");
  return navigation;
}
