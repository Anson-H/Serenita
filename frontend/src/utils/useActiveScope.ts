import { captureAuthContext, isAuthContextCurrent } from "../api/authLifecycle";
import { useEffect, useRef } from "react";

// An old request may finish in the background, but must not update or navigate
// a workspace that now belongs to another member or has been unmounted.
export function useActiveScope(scope: string) {
  const authContext = captureAuthContext();
  const currentScope = useRef({ scope, generation: 0, authContext });
  const mounted = useRef(true);
  if (currentScope.current.scope !== scope || currentScope.current.authContext !== authContext) {
    currentScope.current = { scope, generation: currentScope.current.generation + 1, authContext };
  }
  const generation = currentScope.current.generation;
  useEffect(() => {
    mounted.current = true;
    return () => { mounted.current = false; };
  }, []);
  return () => isAuthContextCurrent(authContext) && mounted.current && currentScope.current.generation === generation;
}
