import { hasNavigationSaves, saveBeforeNavigation } from "../utils/pendingNavigation";
import { useEffect, useRef, useState } from "react";

import { currentRoute, type RoutePath } from "./routes";

export function useBrowserRoute() {
  const [route, setRoute] = useState<RoutePath>(currentRoute);

  const routeRef = useRef(route);
  routeRef.current = route;
  const sequence = useRef(0);

  useEffect(() => {
    async function syncRouteFromHistory() {
      const target = currentRoute();
      const previous = routeRef.current;
      const token = ++sequence.current;
      if (!hasNavigationSaves() || await saveBeforeNavigation()) {
        if (token === sequence.current) setRoute(target);
      } else if (token === sequence.current) {
        window.history.pushState(null, "", previous);
      }
    }

    window.addEventListener("popstate", syncRouteFromHistory);
    return () => window.removeEventListener("popstate", syncRouteFromHistory);
  }, []);

  function navigateTo(path: RoutePath, replace = false) {
    const token = ++sequence.current;
    const commit = () => {
      if (token !== sequence.current) return;
      if (window.location.pathname !== path) {
        const method = replace ? "replaceState" : "pushState";
        window.history[method](null, "", path);
      }
      setRoute(path);
    };
    if (!replace && hasNavigationSaves()) {
      void saveBeforeNavigation().then(saved => { if (saved) commit(); });
    } else commit();
  }

  return {
    route,
    navigateTo
  };
}
