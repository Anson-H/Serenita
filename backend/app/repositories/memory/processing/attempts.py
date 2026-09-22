"""Program-owned latest processing state and conditional execution claims."""
import json

from backend.app.core.errors import SerenitaError
from backend.app.storage.memory.database import MEMORY_DATABASE_SCHEMA

TERMINAL = {'completed', 'failed', 'cancelled'}


def fail(message):
    raise SerenitaError('conflict', 'MEMORY_ATTEMPT_CONFLICT', message)


def validate_updates(repo, db, access, batch):
    created = {item.attempt_id for item in batch.attempts}
    seen = set()
    for update in batch.attempt_updates:
        if update.attempt_id in seen:
            fail('同次写入每个处理任务只能更新一次。')
        seen.add(update.attempt_id)
        if update.attempt_id in created:
            if update.resume or update.expected_updated_commit_id is not None or update.processing_status not in {'pending', 'running'}:
                fail('新处理任务只能登记为等待或开始处理。')
            continue
        current = repo._require(db, access, 'processing_attempt', update.attempt_id)
        if update.resume:
            if (update.expected_updated_commit_id != current['updated_commit_id']
                    or current['processing_status'] != 'failed'
                    or current['task_kind'] != 'event_formation'
                    or update.processing_status != 'running' or update.model_id is not None):
                fail('只有失败的事件形成任务可通过继续处理操作恢复。')
            if db.execute('SELECT 1 FROM processing_attempts WHERE previous_attempt_id=?',
                    (update.attempt_id,)).fetchone():
                fail('此处理已有后续尝试，不能继续旧处理。')
            if db.execute("SELECT 1 FROM processing_attempts WHERE account_id=? AND member_id=? "
                    "AND source_database IS ? AND change_id IS ? AND task_kind='event_formation' "
                    "AND processing_status='completed' LIMIT 1",
                    (access.account_id, access.member_id, current['source_database'], current['change_id'])).fetchone():
                fail('这条变更记录已经全部处理完成，不能继续。')
            from backend.app.repositories.memory.processing.checkpoints import inspect_work
            if not inspect_work(repo, access.actor_account_id, access.member_id, update.attempt_id)['available']:
                fail('没有可复用的执行检查点。')
            continue
        if update.expected_updated_commit_id != current['updated_commit_id'] or current['processing_status'] in TERMINAL:
            fail('处理状态已变化或已经结束。')
        if update.processing_status == 'pending':
            fail('已有处理任务不能重新登记为等待。')
        if update.processing_status == 'running' and current['processing_status'] != 'pending':
            fail('只有等待中的处理任务可以开始。')
        if update.processing_status == 'completed' and current['processing_status'] != 'running':
            fail('只有已经开始的处理任务可以完成。')
        if current['started_commit_id'] and update.model_id is not None:
            fail('已经开始的处理任务不能改变执行参数。')
    for update in batch.attempt_updates:
        if update.model_id is not None and update.processing_status != 'running':
            fail('执行模型必须在开始处理时提供。')


def apply_updates(repo, db, access, batch, commit):
    created = {item.attempt_id for item in batch.attempts}
    updated = {}
    for item in batch.attempt_updates:
        current = repo._require(db, access, 'processing_attempt', item.attempt_id)
        changes = item.model_dump(mode='json', exclude={'attempt_id','expected_updated_commit_id','model_id','resume'})
        changes['updated_commit_id'] = commit['commit_id']
        if item.processing_status == 'running' and not item.resume:
            changes.update(started_commit_id=commit['commit_id'], model_id=item.model_id)
        for field in ('gaps', 'result_references'):
            changes[field+'_json'] = json.dumps(changes.pop(field), ensure_ascii=False, separators=(',', ':'))
        expected = commit['commit_id'] if item.attempt_id in created else item.expected_updated_commit_id
        cursor = db.execute('UPDATE processing_attempts SET '+','.join(key+'=?' for key in changes)+
            ' WHERE attempt_id=? AND account_id=? AND member_id=? AND updated_commit_id=? RETURNING *',
            (*changes.values(), item.attempt_id, access.account_id, access.member_id, expected))
        saved = cursor.fetchone()
        if saved is None:
            fail('处理状态已被其它操作更新。')
        raw = dict(saved)
        MEMORY_DATABASE_SCHEMA.table_by_name['processing_attempts'].validate_values(raw)
        updated[item.attempt_id] = {**raw, 'record_sequence': current['record_sequence'], 'submitted_at': current['submitted_at']}
        for reference in item.result_references:
            repo._require(db, access, reference.object_type, reference.object_id, item_id=reference.item_id, version=reference.version)
    return updated
