import { useEffect, useRef } from "react";
import { ResourceDraft } from "./resourceDraft";
import { registerNavigationSave } from "./pendingNavigation";

type Resource<T> = {
  key: string;
  server: T;
  draft: T;
  save: (value: T) => Promise<T>;
  onError?: (message: string) => void;
};

/** Keeps all edited resources active across tabs and flushes them before navigation. */
export function useResourceAutosave<T>(
  resources: Resource<T>[],
  composing: boolean,
  delay: number,
) {
  const controllers = useRef(
    new Map<string, { draft: ResourceDraft<T>; server: string }>(),
  );
  const current = useRef(resources);
  current.current = resources;
  function synchronize() {
    for (const resource of current.current) {
      const signature = JSON.stringify(resource.server);
      let entry = controllers.current.get(resource.key);
      if (!entry) {
        entry = {
          draft: new ResourceDraft(resource.server),
          server: signature,
        };
        controllers.current.set(resource.key, entry);
      } else if (entry.server !== signature) {
        entry.draft.receive(resource.server);
        entry.server = signature;
      }
      entry.draft.update(resource.draft);
      entry.draft.composition(composing);
    }
  }
  const flushRef = useRef(async () => true);
  flushRef.current = async () => {
    synchronize();
    const results = await Promise.all(
      current.current.map(async (resource) => {
        const controller = controllers.current.get(resource.key)!.draft;
        const saved = await controller.flush((value) => {
          const latest = current.current.find(
            (item) => item.key === resource.key,
          );
          if (!latest) throw new Error("设置作用域已改变。");
          return latest.save(value);
        });
        if (!saved) resource.onError?.(controller.snapshot().error);
        return saved;
      }),
    );
    return results.every(Boolean);
  };
  const signature = JSON.stringify(
    resources.map(({ key, server, draft }) => [key, server, draft]),
  );
  useEffect(() => {
    synchronize();
    if (composing) return;
    const timer = window.setTimeout(() => {
      void flushRef.current();
    }, delay);
    return () => window.clearTimeout(timer);
  }, [signature, composing, delay]);
  useEffect(() => registerNavigationSave(() => flushRef.current()), []);
  return () => flushRef.current();
}
