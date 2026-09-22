import type { ReactNode, Ref } from "react";
import { SidebarExpandedIcon } from "../components/icons";

export function SidebarHeader({ children, title = "Serenita", onCollapseSidebar, onCollapseMobileSidebar, mobileCollapseButtonRef }: {
  children?: ReactNode; title?: string; onCollapseSidebar: () => void; onCollapseMobileSidebar: () => void; mobileCollapseButtonRef?: Ref<HTMLButtonElement>;
}) {
  return <section className="sidebar-header"><div className="brand-row">
    <div className="brand-name"><span>{title}</span></div>
    {children}
    <button aria-label="折叠侧边栏" title="折叠侧边栏" className="control control--titlebar control--icon control--ghost sidebar-collapse-button titlebar-icon-control" onClick={onCollapseSidebar} type="button"><SidebarExpandedIcon /></button>
    <button aria-label="折叠侧边栏" title="折叠侧边栏" className="control control--titlebar control--icon control--ghost mobile-sidebar-collapse-button titlebar-icon-control" onClick={onCollapseMobileSidebar} ref={mobileCollapseButtonRef} type="button"><SidebarExpandedIcon /></button>
  </div></section>;
}
