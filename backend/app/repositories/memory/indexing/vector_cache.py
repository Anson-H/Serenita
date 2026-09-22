"""Persist vectors produced by one draft before publication."""

def persist_vectors(stage):
    stage.work.put('_vectors', [{'index_name': group['store'].index_name,
        'space': group['space'], 'rows': group['rows']} for group in stage.vectors.values()])


def cached_row(store, account, space, identity):
    from backend.app.repositories.memory.processing.staging_scope import staging
    stage = staging()
    if stage is None or stage.account != account:
        return None
    return stage.vectors.get((store.index_name, space['space_id']), {}).get('rows', {}).get(identity)


def cache_vector(store, account, space, row):
    from backend.app.repositories.memory.processing.staging_scope import staging
    stage = staging()
    if stage is None or stage.account != account:
        return False
    if row.get('account_id') != account or row.get('member_id') != stage.member:
        raise RuntimeError('Cached vector belongs to a different member')
    group = stage.vectors.setdefault((store.index_name, space['space_id']),
        {'store': store, 'space': dict(space), 'rows': {}})
    previous = group['rows'].get(row['vector_id'])
    if previous is not None and previous != row:
        raise RuntimeError('Cached vector identity has conflicting content')
    group['rows'][row['vector_id']] = dict(row)
    try:
        persist_vectors(stage)
    except BaseException:
        if previous is None:
            group['rows'].pop(row['vector_id'], None)
        else:
            group['rows'][row['vector_id']] = previous
        raise
    return True

