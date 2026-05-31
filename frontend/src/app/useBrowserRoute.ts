import { useEffect, useState } from "react";

import { currentRoute, type RoutePath } from "./routes";

export function useBrowserRoute() {
  const [route, setRoute] = useState<RoutePath>(currentRoute);

  useEffect(() => {
    function syncRouteFromHistory() {
      setRoute(currentRoute());
    }

    window.addEventListener("popstate", syncRouteFromHistory);
    return () => window.removeEventListener("popstate", syncRouteFromHistory);
  }, []);

  function navigateTo(path: RoutePath, replace = false) {
    if (window.location.pathname !== path) {
      const method = replace ? "replaceState" : "pushState";
      window.history[method](null, "", path);
    }
    setRoute(path);
  }

  return {
    route,
    navigateTo
  };
}
