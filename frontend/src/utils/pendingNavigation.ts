/** Editors register a short persistence barrier before leaving their scope. */
const barriers = new Set<() => Promise<boolean>>();
export function registerNavigationSave(save: () => Promise<boolean>) {
  barriers.add(save);
  return () => { barriers.delete(save); };
}
export const hasNavigationSaves = () => barriers.size > 0;
export async function saveBeforeNavigation() {
  for (const save of [...barriers]) if (!await save()) return false;
  return true;
}
