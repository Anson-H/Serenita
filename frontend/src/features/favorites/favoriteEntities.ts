import type { Favorite } from "../../api/client";

type Snapshot = { favorites: Favorite[]; selectedId: string | null };
type Update<T> = T | ((current: T) => T);

/** The list, detail and tag editor all read and update the same entities. */
export class FavoriteEntities {
  private state: Snapshot = { favorites: [], selectedId: null };
  private listeners = new Set<() => void>();
  private tagRevisions = new Map<string, number>();
  snapshot = () => this.state;
  subscribe = (listener: () => void) => { this.listeners.add(listener); return () => { this.listeners.delete(listener); }; };
  detail = () => this.get(this.state.selectedId ?? "") ?? null;
  get = (id: string) => this.state.favorites.find(item => item.favorite_id === id);
  tagRevision = (id: string) => this.tagRevisions.get(id) ?? 0;
  private publish(favorites: Favorite[], selectedId = this.state.selectedId) {
    if (selectedId === this.state.selectedId && favorites.length === this.state.favorites.length && favorites.every((item, index) => item === this.state.favorites[index])) return;
    for (const item of favorites) {
      if (JSON.stringify(this.get(item.favorite_id)?.tags) !== JSON.stringify(item.tags))
        this.tagRevisions.set(item.favorite_id, this.tagRevision(item.favorite_id) + 1);
    }
    this.state = { favorites, selectedId: favorites.some(item => item.favorite_id === selectedId) ? selectedId : null };
    for (const listener of this.listeners) listener();
  }
  updateList = (next: Update<Favorite[]>) => this.publish(typeof next === "function" ? next(this.state.favorites) : next);
  updateDetail = (next: Update<Favorite | null>) => {
    const detail = typeof next === "function" ? next(this.detail()) : next;
    if (detail === this.detail()) return;
    if (!detail) { this.publish(this.state.favorites, null); return; }
    this.publish(this.state.favorites.map(item => item.favorite_id === detail.favorite_id ? { ...item, ...detail } : item), detail.favorite_id);
  };
  acceptDetail = (detail: Favorite, tagRevision: number) => {
    const current = this.get(detail.favorite_id);
    if (!current) return;
    this.updateDetail({ ...current, ...detail, tags: this.tagRevision(detail.favorite_id) === tagRevision ? detail.tags : current.tags });
  };
  clear = () => { this.tagRevisions.clear(); this.publish([], null); };
}
