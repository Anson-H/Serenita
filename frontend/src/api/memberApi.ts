import { API_BASE_URL, request } from "./request";

export type MemberFields = {
  member_name: string;
  sex: "male" | "female" | "other" | null;
  birth_date: string | null;
  blood_type: "a" | "b" | "ab" | "o" | "other" | null;
};

export type Member = MemberFields & {
  member_id: string;
  account_id: string;
  owner_account: string;
  is_default: boolean;
  is_owned: boolean;
  permission: "owner" | "read" | "edit";
  can_edit: boolean;
};

export type MemberCollection = {
  members: Member[];
  default_member_id: string | null;
  startup_mode: "default" | "last_used";
  last_member_id: string | null;
  initial_member_id: string | null;
  access_revision: number;
};

export type MemberGrant = {
  member_id: string;
  account_id: string;
  grantee_account: string;
  grantee_account_name: string;
  permission: "read" | "edit";
};

export const fetchMembers = (signal?: AbortSignal) => request<MemberCollection>("/members", { signal });

export type MemberSaveInput = MemberFields & { set_as_default?: boolean };

export type MemberDeletion = { member_id: string; deleted: true; pending_file_cleanup: number; collection: MemberCollection };

export const deleteMember = (id: string) => request<MemberDeletion>(`/members/${encodeURIComponent(id)}`, { method: "DELETE" });

export const createMember = (input: MemberSaveInput) => request<Member>("/members", { method: "POST", body: JSON.stringify(input) });

export const updateMember = (id: string, input: MemberSaveInput) => request<Member>(`/members/${encodeURIComponent(id)}`, { method: "PATCH", body: JSON.stringify(input) });

export const saveMemberPreferences = (input: { startup_mode?: "default" | "last_used"; last_member_id?: string | null; default_member_id?: string }) => request<MemberCollection>("/account-settings/member-preferences", { method: "PATCH", body: JSON.stringify(input) });

export const fetchMemberGrants = () => request<{ grants: MemberGrant[] }>("/account-settings/member-grants");

export const setMemberGrants = (grantee_account: string, grants: Array<{ member_id: string; permission: "read" | "edit" }>) => request<{ grants: MemberGrant[] }>("/account-settings/member-grants", { method: "PUT", body: JSON.stringify({ grantee_account, grants }) });

export const revokeMemberGrant = (member: string, grantee: string) => request<{ grants: MemberGrant[] }>(`/account-settings/member-grants/${encodeURIComponent(member)}/${encodeURIComponent(grantee)}`, { method: "DELETE" });

export function subscribeMemberAccess(onChange: () => void) {
  const controller = new AbortController();
  let active = true;
  const events = new EventSource(`${API_BASE_URL}/members/access-events`, { withCredentials: true });
  events.addEventListener("member_access", onChange);
  events.addEventListener("open", onChange);
  // EventSource hides HTTP status; a normal request resolves authentication on failure.
  const onError = () => { void fetchMembers(controller.signal).then(() => { if (active) onChange(); }).catch(() => undefined); };
  events.addEventListener("error", onError);
  return () => {
    active = false;
    controller.abort();
    events.removeEventListener("member_access", onChange);
    events.removeEventListener("open", onChange);
    events.removeEventListener("error", onError);
    events.close();
  };
}
