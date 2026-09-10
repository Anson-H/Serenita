import {request, API_BASE_URL} from './request';
export type NotificationSwitch = 'notifications_enabled'|'medication_due_enabled'|'medication_expired_enabled'|'answer_completed_enabled';
export type NotificationPreferenceChanges = Partial<Record<NotificationSwitch,boolean>>;
export type NotificationPreferences = Record<NotificationSwitch,boolean> & {
  notifications_enabled_since:string|null;medication_due_enabled_since:string|null;
  medication_expired_enabled_since:string|null;answer_completed_enabled_since:string|null;notifications_updated_at:string;
};
export type NotificationStatus = 'pending'|'read';
export type NotificationAction = 'read';
export type NotificationItem = {
  notification_id:string;notification_type:string;member_id:string|null;resource_type:string|null;resource_id:string|null;
  occurred_at:string;available_at:string;title:string;message:string;status:NotificationStatus;event_revision:number;
  details:{label:string;text:string}[];target:{medication_id?:string;member_id:string|null;resource_type:string|null;resource_id:string|null};actions:NotificationAction[];
};
export type NotificationError = {code:string;message:string};
export type NotificationPage = {items:NotificationItem[];next_cursor:string|null;errors:NotificationError[]};
export const readNotificationPreferences = (signal?:AbortSignal) => request<NotificationPreferences>('/account-settings/notifications',{signal});
export const saveNotificationPreferences = (changes:NotificationPreferenceChanges) => request<NotificationPreferences>('/account-settings/notifications',{method:'PUT',body:JSON.stringify(changes)});
export const readNotifications = (status:NotificationStatus='pending',cursor?:string|null,signal?:AbortSignal) => request<NotificationPage>('/notifications?'+new URLSearchParams({status,...(cursor?{cursor}:{})}),{signal});
export const readNotificationSummary = (signal?:AbortSignal) => request<{pending_count:number|null;errors:NotificationError[]}>('/notifications/summary',{signal});
export const actNotification = (notification_id:string,action:NotificationAction) => request('/notifications/'+encodeURIComponent(notification_id)+'/actions',{method:'POST',body:JSON.stringify({action})});
export const openNotificationEvents = () => new EventSource(`${API_BASE_URL}/notifications/events`,{withCredentials:true});
