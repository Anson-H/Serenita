export type AuthContext = Readonly<{ accountId: string | null; generation: number }>;
let current: AuthContext = { accountId: null, generation: 0 };
const listeners = new Set<() => void>();

export function captureAuthContext(): AuthContext { return current; }
export function isAuthContextCurrent(context: AuthContext) { return context === current; }
export function advanceAuthLifecycle(accountId: string | null = current.accountId) {
  current = { accountId, generation: current.generation + 1 };
  for (const listener of listeners) listener();
}
export function setAuthenticatedAccount(accountId: string | null) {
  if (current.accountId !== accountId) advanceAuthLifecycle(accountId);
}
export function subscribeAuthLifecycle(listener: () => void) {
  listeners.add(listener);
  return () => { listeners.delete(listener); };
}
export function assertAuthContext(context: AuthContext) {
  if (!isAuthContextCurrent(context)) {
    const error = new Error('请求所属账号会话已改变。');
    error.name = 'AbortError';
    throw error;
  }
}
