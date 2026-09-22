import { randomUuid } from "../../utils/randomUuid";
import { apiUrl, request } from "../transport/request";
import type { AuthenticatedSession } from "../types";

const GUEST_STORAGE_KEY = "serenita:guest-identity";
const GUEST_ACCOUNT_PATTERN = /^guest_[0-9a-f]{14}$/;

type GuestIdentity = {
  account: string;
  password: string;
};

let memoryIdentity: GuestIdentity | null = null;

function validIdentity(value: unknown): value is GuestIdentity {
  if (!value || typeof value !== "object") return false;
  const candidate = value as Partial<GuestIdentity>;
  return typeof candidate.account === "string"
    && GUEST_ACCOUNT_PATTERN.test(candidate.account)
    && typeof candidate.password === "string"
    && candidate.password.length > 0;
}

function createIdentity(): GuestIdentity {
  return {
    account: `guest_${randomUuid().replaceAll("-", "").slice(0, 14)}`,
    password: `${randomUuid()}${randomUuid()}`
  };
}

function guestIdentity(): GuestIdentity {
  if (memoryIdentity) return memoryIdentity;
  if (typeof window === "undefined") return (memoryIdentity = createIdentity());
  try {
    const stored = JSON.parse(window.localStorage.getItem(GUEST_STORAGE_KEY) ?? "null");
    if (validIdentity(stored)) {
      memoryIdentity = stored;
      return stored;
    }
  } catch {
    // Generate an in-memory identity when browser storage is unavailable.
  }

  const created = createIdentity();
  memoryIdentity = created;
  try {
    window.localStorage.setItem(GUEST_STORAGE_KEY, JSON.stringify(created));
  } catch {
    // The current page can still use the identity until it is closed.
  }
  return created;
}

export function openGuestSession() {
  const identity = guestIdentity();
  return request<AuthenticatedSession>("/auth/guest", {
    method: "POST",
    body: JSON.stringify(identity)
  });
}

export function closeGuestSessionNow() {
  return request<{ success: boolean; deleted: boolean }>("/auth/guest/close", {
    method: "POST",
    body: "{}"
  });
}

export function notifyGuestPageClosed() {
  if (typeof window === "undefined") return;
  const url = apiUrl("/auth/guest/close");
  try {
    if (navigator.sendBeacon(url, "")) return;
  } catch {
    // Use a keepalive request when Beacon is unavailable.
  }
  void fetch(url, {
    method: "POST",
    credentials: "include",
    keepalive: true,
    body: ""
  }).catch(() => undefined);
}
