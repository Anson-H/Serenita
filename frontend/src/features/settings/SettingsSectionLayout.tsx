import { type ReactNode } from "react";
import { WorkspaceToolbar } from "../../components/WorkspaceToolbar";
import { ChevronLeftIcon } from "../../components/icons";
import { useDeployment } from "../../app/DeploymentContext";
import { navigationLabels } from "../../components/navigationLabels";
import { SettingsDetailPanel } from "./SettingsDetailPanel";
import { useSettingsNavigation } from "./SettingsNavigationContext";

/** Responsive presentation of one setting area; no account or provider state. */
export function SettingsSectionLayout({ title, toolbarTitle = title, onBack, secondaryList, wide = false, children }: {
  title: string; toolbarTitle?: string; onBack?: () => void; secondaryList?: ReactNode; wide?: boolean; children: ReactNode;
}) {
  const { actions, mobileSidebarToggle } = useSettingsNavigation();
  const { detailOpen, mobileLayer, goBackSettingsLayer, closeSettingsDetail, settingsMobileLayerTitle } = actions;
  const local = useDeployment().mode === "self_hosted";
  return <>
    <WorkspaceToolbar className="settings-toolbar" title={toolbarTitle} onBack={onBack ?? (secondaryList && detailOpen ? closeSettingsDetail : undefined)} />
    <div className="settings-content-body">
      <div aria-hidden={detailOpen ? true : undefined} className="settings-mobile-layer-header" inert={detailOpen ? true : undefined}>
        {mobileLayer === "root" ? mobileSidebarToggle ?? <span aria-hidden="true" /> : <button aria-label="返回上一级"
          className="control control--titlebar control--icon control--ghost workspace-back-control settings-mobile-back-button titlebar-icon-control"
          onClick={goBackSettingsLayer} type="button"><ChevronLeftIcon /></button>}
        <strong>{local && mobileLayer === "root" ? navigationLabels.localSettings : settingsMobileLayerTitle()}</strong><span aria-hidden="true" />
      </div>
      {secondaryList}
      <SettingsDetailPanel mobileOpen={detailOpen} onBack={onBack ?? closeSettingsDetail} title={title} wide={wide}>{children}</SettingsDetailPanel>
    </div>
  </>;
}
