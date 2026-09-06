import { assertAuthContext, captureAuthContext } from "./authLifecycle";
import { publishAuthInvalidation } from "./authSessionEvents";

export const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? "/api").replace(/\/$/, "");

function apiTargetDescription() {
  const origin = typeof window === "undefined" ? "http://localhost" : window.location.origin;
  return new URL(API_BASE_URL, origin).href;
}

export function networkFailureMessage(error: unknown) {
  const detail = error instanceof Error && error.message ? `（${error.message}）` : "";
  return `无法连接后端服务${detail}。当前 API 地址为 ${apiTargetDescription()}，请检查网络和服务状态。`;
}

export function serverFailureMessage(response: Pick<Response, "status">) {
  return `后端服务返回 ${response.status}。当前 API 地址为 ${apiTargetDescription()}，请检查后端服务日志。`;
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
    throw new Error(networkFailureMessage(error));
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
