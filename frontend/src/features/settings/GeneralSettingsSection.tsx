import { useLayoutEffect, useRef } from "react";
import { MemorySettings, memorySettingsTitles, type MemorySettingsPage } from "./memory/MemorySettings";
import { ThemeSettings } from "./theme/ThemeSettings";
import { MembersPanel } from "../members/MemberSettings";
import { navigationLabels } from "../../components/navigationLabels";
import { SettingsSectionLayout } from "./SettingsSectionLayout";
import { useSettingsNavigation } from "./SettingsNavigationContext";
export function GeneralSettingsSection() {
  const { location, navigateSettings } = useSettingsNavigation();
  const memoryPage = location.section === "memory" ? location.page : "root";
  const content = useRef<HTMLDivElement | null>(null);
  useLayoutEffect(() => { content.current?.closest(".settings-detail-panel-body")?.scrollTo(0, 0); }, [memoryPage]);
  if (location.section === "memory") {
    const navigate = (page: MemorySettingsPage, memberId = location.memberId) => navigateSettings({ section: "memory", page, memberId });
    return <SettingsSectionLayout title={memorySettingsTitles[memoryPage]} onBack={memoryPage !== "root" ? () => navigate("root") : undefined}>
      <div className="settings-detail-column" ref={content}><MemorySettings page={memoryPage} memberId={location.memberId} onNavigate={navigate} /></div>
    </SettingsSectionLayout>;
  }
  if (location.section === "theme") return <SettingsSectionLayout title={navigationLabels.theme}><div className="settings-detail-column"><ThemeSettings /></div></SettingsSectionLayout>;
  if (location.section === "members") return <SettingsSectionLayout title={navigationLabels.health}><div className="settings-detail-column"><MembersPanel /></div></SettingsSectionLayout>;
  return null;
}
