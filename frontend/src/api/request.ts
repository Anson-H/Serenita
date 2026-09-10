import { assertAuthContext, captureAuthContext } from "./authLifecycle";
import { publishAuthInvalidation } from "./authSessionEvents";

export const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? "/api").replace(/\/$/, "");

export const apiUrl = (path: string) => `${API_BASE_URL}${path}`;

export function networkFailureMessage(_error: unknown) {
  return '连接中断，操作尚未完成。请检查网络后重试。';
}

export function serverFailureMessage(_response: Pick<Response, "status">) {
  return '服务暂时无法完成操作。请稍后重试。';
}

export type ApiErrorDetail = {
  code?: string;
  message?: string;
  [key: string]: unknown;
};

export class ApiRequestError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly detail: ApiErrorDetail | null
  ) {
    super(message);
    this.name = "ApiRequestError";
  }
}

function objectValue(value: unknown): ApiErrorDetail | null {
  return value !== null && typeof value === "object" && !Array.isArray(value)
    ? value as ApiErrorDetail : null;
}

export function apiResponseError(status: number, body: unknown): ApiRequestError {
  const envelope = objectValue(body);
  const detail = objectValue(envelope?.detail) ?? envelope;
  const code = typeof detail?.code === "string" ? detail.code : undefined;
  let message = typeof envelope?.detail === "string" ? envelope.detail
    : typeof detail?.message === "string" ? detail.message
      : code ?? (status >= 500 ? serverFailureMessage({ status }) : `请求失败：${status}`);
  publishAuthInvalidation(status, code);
  if (code === "MEMBER_ACCESS_UNAVAILABLE" && typeof window !== "undefined") {
    window.dispatchEvent(new Event("serenita:member-access-changed"));
    message = "";
  }
  return new ApiRequestError(message, status, detail);
}

export async function requestResponse(path: string, init?: RequestInit): Promise<Response> {
  const context = captureAuthContext();
  const headers = new Headers(init?.headers);
  if (context.accountId && !["GET", "HEAD", "OPTIONS"].includes((init?.method ?? "GET").toUpperCase())) {
    headers.set("X-Serenita-Account-ID", context.accountId);
  }
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, { ...init, headers, credentials: "include" });
  } catch (error) {
    assertAuthContext(context);
    if (error instanceof Error && error.name === "AbortError") throw error;
    throw new Error(networkFailureMessage(error), {cause:error});
  }
  assertAuthContext(context);
  if (!response.ok) {
    let body: unknown = null;
    try { body = await response.json(); } catch { /* Status still identifies non-JSON errors. */ }
    assertAuthContext(context);
    throw apiResponseError(response.status, body);
  }
  return response;
}

export async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const context = captureAuthContext();
  const response = await requestResponse(path, {
    ...init,
    headers: {
      ...(init?.body instanceof FormData ? {} : { "Content-Type": "application/json" }),
      ...(init?.headers ?? {})
    }
  });
  const body = await response.json() as T;
  assertAuthContext(context);
  return body;
}
