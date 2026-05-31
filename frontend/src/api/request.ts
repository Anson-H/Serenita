import { getSessionToken } from "./sessionToken";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "/api";
const LOCAL_BACKEND_URL = "http://127.0.0.1:8000";
const LOCAL_DEV_FRONTEND_URLS = "http://127.0.0.1:5173 或 http://localhost:5173";

function pageOrigin() {
  return typeof window === "undefined" ? "未知页面地址" : window.location.origin;
}

function apiRunHint() {
  if (API_BASE_URL.startsWith("/")) {
    return `请确认后端已在 ${LOCAL_BACKEND_URL} 运行，并从 ${LOCAL_DEV_FRONTEND_URLS} 打开前端。当前页面地址为 ${pageOrigin()}；如果当前页面是临时预览或测试端口，请关闭该页面并切回 5173。`;
  }
  return `当前使用 VITE_API_BASE_URL=${API_BASE_URL}，请确认该地址能访问后端。当前页面地址为 ${pageOrigin()}。`;
}

export function apiTargetDescription() {
  if (API_BASE_URL.startsWith("/")) {
    return `${pageOrigin()}${API_BASE_URL}（由 Vite 代理到 http://127.0.0.1:8000）`;
  }
  return new URL(API_BASE_URL).origin;
}

export function networkFailureMessage(error: unknown) {
  const detail = error instanceof Error && error.message ? `（${error.message}）` : "";
  return `无法连接后端服务${detail}。当前 API 地址为 ${apiTargetDescription()}。${apiRunHint()}`;
}

export function serverFailureMessage(response: Response) {
  return `后端服务返回 ${response.status}。如果你正在本地开发，这通常表示后端未启动、Vite 代理无法连接到 ${LOCAL_BACKEND_URL}，或后端内部异常。当前 API 地址为 ${apiTargetDescription()}。${apiRunHint()}请检查后端终端日志。`;
}

export async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const token = getSessionToken();
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      headers: {
        ...(init?.body instanceof FormData ? {} : { "Content-Type": "application/json" }),
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...(init?.headers ?? {})
      },
      ...init
    });
  } catch (error) {
    throw new Error(networkFailureMessage(error));
  }

  if (!response.ok) {
    let message = `请求失败：${response.status}`;
    try {
      const errorBody = await response.json();
      if (typeof errorBody.detail === "string") {
        message = errorBody.detail;
      } else if (errorBody.detail?.message) {
        message = errorBody.detail.message;
      } else if (errorBody.detail?.code) {
        message = errorBody.detail.code;
      }
    } catch {
      if (response.status >= 500) {
        message = serverFailureMessage(response);
      }
    }
    throw new Error(message);
  }

  return response.json() as Promise<T>;
}
