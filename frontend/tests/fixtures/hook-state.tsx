import { act, useState } from "react";
import { createRoot } from "react-dom/client";
import { useListContextMenu } from "../../src/components/useListContextMenu";

Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true });
export { act };
export { apiClient } from "../../src/api/client";

// Exercise real React effects, batching and cleanup without reproducing its hook internals.
export function mountHook<A, T>(hook: (args: A) => T, args: NoInfer<A>) {
  const host = document.body.appendChild(document.createElement("div"));
  const root = createRoot(host);
  let value: T;
  function Probe({ args }: { args: A }) { value = hook(args); return null; }
  const render = (args: A) => act(() => root.render(<Probe args={args} />));
  render(args);
  return { get current() { return value!; }, render, unmount: () => act(() => { root.unmount(); host.remove(); }) };
}

function MenuDemo() {
  const [scope, setScope] = useState("reports");
  const [enabled, setEnabled] = useState(true);
  const [opened, setOpened] = useState(0);
  const [removed, setRemoved] = useState(false);
  const menu = useListContextMenu({ scope, enabled });
  return <>
    <button onClick={() => setScope(value => value === "reports" ? "items" : "reports")}>切换目录</button>
    <button onClick={() => setEnabled(value => !value)}>切换启用</button>
    <button onClick={() => setRemoved(true)}>移除入口</button>
    <div id="ancestor" style={{ height: 120, overflow: "auto", marginTop: 20 }}>
      <div id="row" {...menu.rowProps("report", ".open")} style={{ height: 800 }}>
        {!removed && <button className="open" onClick={() => setOpened(value => value + 1)}>打开报告</button>}
      </div>
    </div>
    <div id="unrelated" style={{ height: 30, overflow: "auto" }}><div style={{ height: 300 }}>无关列表</div></div>
    <output aria-label="打开次数">{opened}</output>
    {menu.contextMenu && <div role="menu" ref={menu.menuRef} onKeyDown={menu.onMenuKeyDown}
      style={{ position: "fixed", left: menu.contextMenu.x, top: menu.contextMenu.y, width: 176, height: 82 }}>
      <button role="menuitem">编辑报告</button>
    </div>}
  </>;
}
if (location.hash === "#menu") {
  Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: false });
  createRoot(document.body.appendChild(document.createElement("div"))).render(<MenuDemo />);
}
document.body.dataset.ready = "true";
