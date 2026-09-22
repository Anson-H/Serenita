"""Live action projection shared by processing details and change catalogs."""


def project_processing_actions(repository, actor, member, row, *, live, successor, completed_change):
    formation = row['task_kind'] == 'event_formation'
    state = row.get('processing_status')
    eligible = bool(live and not successor and not completed_change)
    recovery = {'checkpoint': None, 'recovery_status': None, 'recovery_reason': None, 'available': False}
    row['recovery_records'] = []
    if formation:
        from backend.app.repositories.memory.processing.checkpoints import inspect_work, read_recoveries
        recovery = inspect_work(repository, actor, member, row['attempt_id'])
        row['recovery_records'] = read_recoveries(repository, actor, member, row['attempt_id'])
    row.update({key: recovery[key] for key in ('checkpoint', 'recovery_status', 'recovery_reason')})
    if formation and state in {'failed', 'cancelled'}:
        if successor:
            row['recovery_reason'] = '此处理已有后续尝试，请查看最新处理结果。'
        elif completed_change:
            row['recovery_reason'] = '这条变更记录已处理完成，不能继续或从头重新处理。'
        elif not live:
            row['recovery_reason'] = '当前读取范围不允许执行恢复操作。'
        elif state == 'cancelled':
            row['recovery_reason'] = '这次处理已取消，需要处理时请选择从头重新处理。'
    row['available_actions'] = {
        'resume': bool(eligible and formation and state == 'failed' and recovery['available']),
        'retry': bool(eligible and row['task_kind'] in {'event_formation', 'vector_index'}
                      and state in {'failed', 'cancelled'}),
        'cancel': bool(eligible and state in {'pending', 'running'}),
    }
