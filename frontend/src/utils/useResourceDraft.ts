import { useEffect, useMemo, useRef, useSyncExternalStore } from "react";
import { registerNavigationSave } from "./pendingNavigation";
import { ResourceDraft } from "./resourceDraft";

export function useResourceDraft<T>({
  resourceKey,
  server,
  save,
  validate,
  editing = false,
  saveEnabled = true,
  beforeNavigate,
}: {
  resourceKey: string;
  server: T;
  save: (value: T) => Promise<T>;
  validate?: (value: T) => string;
  editing?: boolean;
  saveEnabled?: boolean;
  beforeNavigate?: () => Promise<boolean>;
}) {
  const controller = useMemo(() => new ResourceDraft(server), [resourceKey]);
  const options = useRef({ save, validate, saveEnabled, beforeNavigate });
  options.current = { save, validate, saveEnabled, beforeNavigate };
  const state = useSyncExternalStore(
    controller.subscribe,
    controller.snapshot,
    controller.snapshot,
  );
  const flush = () =>
    !options.current.saveEnabled ? Promise.resolve(true) : controller.flush(
      (value) => options.current.save(value),
      (value) => options.current.validate?.(value) || "",
    );
  useEffect(() => {
    controller.receive(server, editing);
  }, [controller, server]);
  useEffect(() => {
    if (!editing) controller.receive(controller.snapshot().server);
  }, [controller, editing]);
  useEffect(
    () =>
      registerNavigationSave(async () => {
        if (options.current.beforeNavigate && !await options.current.beforeNavigate()) return false;
        return !options.current.saveEnabled ? true : controller.flush(
          (value) => options.current.save(value),
          (value) => options.current.validate?.(value) || "",
        );
      },
      ),
    [controller],
  );
  return { ...state, update: controller.update, flush, controller };
}
