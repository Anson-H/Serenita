import { createContext, useContext, useRef, type HTMLAttributes, type Ref } from "react";
import { captureScrollPosition, restoreScrollPosition, type ScrollPositionSnapshot } from "../utils/inputMethod";
type ScrollControls = { capture: () => ScrollPositionSnapshot | null; reset: () => void; restore: (snapshot: ScrollPositionSnapshot | null) => void };
const ScrollContext = createContext<ScrollControls | null>(null);
export function ScrollRegion({ children, ref, ...props }: HTMLAttributes<HTMLDivElement> & { ref?: Ref<HTMLDivElement> }) {
  const element = useRef<HTMLDivElement | null>(null);
  return <ScrollContext.Provider value={{ capture: () => captureScrollPosition(element.current), reset: () => { if (element.current) element.current.scrollTop = 0; }, restore: restoreScrollPosition }}>
    <div {...props} ref={node => { element.current = node; if (typeof ref === "function") ref(node); else if (ref) ref.current = node; }}>{children}</div>
  </ScrollContext.Provider>;
}
export const useScrollRegion = () => useContext(ScrollContext);
