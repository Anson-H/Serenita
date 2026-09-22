import { hasNavigationSaves, saveBeforeNavigation } from "../utils/pendingNavigation";
import { useEffect, useRef, useState } from "react";

import { currentRoute, type RoutePath } from "./routes";

export function useBrowserRoute<Path extends string = RoutePath>(readRoute: () => Path = currentRoute as () => Path) {
  const [route, setRoute] = useState<Path>(readRoute);

  const routeRef = useRef(route);
  routeRef.current = route;
  const sequence = useRef(0);

  useEffect(() => {
    async function syncRouteFromHistory() {
      const target = readRoute();
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

  function navigateTo(path: Path, replace = false) {
    const token = ++sequence.current;
    const commit = () => {
      if (token !== sequence.current) return;
      if (window.location.pathname + window.location.search !== path) {
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
