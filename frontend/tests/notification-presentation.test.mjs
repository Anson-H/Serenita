import assert from 'node:assert/strict';
import test from 'node:test';
import { loadModule } from './helpers/load-module.mjs';

const { notificationTime, notificationTimeRefreshDelay } = loadModule('features/notifications/notificationPresentation.ts');
const occurred = '2026-09-08T00:00:00Z';
const start = Date.parse(occurred);

test('notification age switches at minute, hour and day boundaries', () => {
  for (const [elapsed, label] of [
    [0, '刚刚'], [59_999, '刚刚'], [60_000, '1分钟前'],
    [3_599_999, '59分钟前'], [3_600_000, '1小时前'],
    [86_399_999, '23小时前'], [86_400_000, '1天前'],
    [3 * 86_400_000, '3天前'],
  ]) assert.equal(notificationTime(occurred, start + elapsed), label);
  assert.equal(notificationTime('2026-09-08T08:00:00+08:00', start + 60_000), '1分钟前');
  assert.equal(notificationTime(occurred, start - 5_000), '刚刚');
  assert.equal(notificationTime('invalid', start), '');
});

test('an open notification refreshes when its displayed age changes', () => {
  for (const elapsed of [59_500, 3_599_500, 86_399_500]) {
    const before = notificationTime(occurred, start + elapsed);
    const delay = notificationTimeRefreshDelay(occurred, start + elapsed);
    assert.equal(delay, 500);
    assert.notEqual(notificationTime(occurred, start + elapsed + delay), before);
  }
});
