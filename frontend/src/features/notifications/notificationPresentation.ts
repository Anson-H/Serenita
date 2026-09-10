import type { NotificationItem } from '../../api/notificationApi';

export function orderedNotifications(items: NotificationItem[]) {
  return [...new Map(items.map(item => [item.notification_id, item])).values()].sort((a, b) =>
    Number(a.status === 'read') - Number(b.status === 'read')
    || Date.parse(b.occurred_at) - Date.parse(a.occurred_at)
    || b.notification_id.localeCompare(a.notification_id)
  );
}

export function notificationTime(value: string, now = Date.now()) {
  const occurred = Date.parse(value);
  if (!Number.isFinite(occurred)) return '';
  const elapsed = Math.max(0, now - occurred);
  if (elapsed < 60_000) return '刚刚';
  if (elapsed < 3_600_000) return `${Math.floor(elapsed / 60_000)}分钟前`;
  if (elapsed < 86_400_000) return `${Math.floor(elapsed / 3_600_000)}小时前`;
  return `${Math.floor(elapsed / 86_400_000)}天前`;
}

export function notificationTimeRefreshDelay(value: string, now: number) {
  const elapsed = now - Date.parse(value);
  if (!Number.isFinite(elapsed) || elapsed < 0) return 60_000;
  const unit = elapsed < 3_600_000 ? 60_000 : elapsed < 86_400_000 ? 3_600_000 : 86_400_000;
  return unit - elapsed % unit;
}
