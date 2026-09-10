import { useRef, useSyncExternalStore } from "react";
import { captureAuthContext, isAuthContextCurrent } from "../../api/authLifecycle";
import { emptyModelCatalog, fetchModelCatalog, type ModelCatalog } from "./modelCatalog";

export class ModelCatalogState {
  private value = emptyModelCatalog();
  private revision = 0;
  private request = 0;
  private listeners = new Set<() => void>();
  constructor(private read = fetchModelCatalog) {}
  snapshot = () => this.value;
  subscribe = (listener: () => void) => { this.listeners.add(listener); return () => { this.listeners.delete(listener); }; };
  update = (next: ModelCatalog | ((current: ModelCatalog) => ModelCatalog)) => {
    this.revision++;
    this.value = typeof next === "function" ? next(this.value) : next;
    for (const listener of this.listeners) listener();
  };
  refresh = async (isRelevant: () => boolean = () => true): Promise<void> => {
    const request = ++this.request, revision = this.revision, auth = captureAuthContext();
    let result: ModelCatalog;
    try { result = await this.read(); }
    catch (error) {
      if (!isAuthContextCurrent(auth) || !isRelevant() || request !== this.request) return;
      if (revision !== this.revision) return this.refresh(isRelevant);
      throw error;
    }
    if (!isAuthContextCurrent(auth) || !isRelevant() || request !== this.request) return;
    // A write accepted after this read began owns the newer state. Read again
    // so changes to other catalog entries are still incorporated.
    if (revision !== this.revision) return this.refresh(isRelevant);
    this.update(result);
  };
}

export function useModelCatalog() {
  const controller = useRef(new ModelCatalogState()).current;
  const modelCatalog = useSyncExternalStore(controller.subscribe, controller.snapshot, controller.snapshot);
  return { modelCatalog, setModelCatalog: controller.update, refreshModelCatalog: controller.refresh };
}
