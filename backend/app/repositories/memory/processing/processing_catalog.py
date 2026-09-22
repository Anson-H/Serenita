"""Read-only business-change grouping of immutable processing records."""
from backend.app.core.errors import SerenitaError
from collections import defaultdict

from backend.app.storage.memory.database import MEMORY_OBJECTS


KINDS = ('event', 'processing_attempt',
         'vector_binding', 'vector_space')


def group_processing(rows, changes):
    by_kind = defaultdict(dict)
    for row in rows:
        by_kind[row['object_type']][row[MEMORY_OBJECTS[row['object_type']][1]]] = row
    events = by_kind['event']
    change_events = defaultdict(set)
    for event_id, event in events.items():
        for evidence in event.get('evidence', []):
            change_events[(evidence['source_database'],evidence['change_id'])].add(event_id)
    def reference_events(ref):
        kind, identity = ref.get('object_type'), ref.get('object_id')
        if kind == 'event':
            return {identity} if identity in events else set()
        if kind in ('vector_binding', 'vector_status'):
            binding = by_kind['vector_binding'].get(identity, {})
            return reference_events({'object_type': 'event', 'object_id': binding.get('event_id')})
        return set()

    attempts = by_kind['processing_attempt']
    attempt_events = {}
    for identity, row in attempts.items():
        linked = set(change_events[(row.get('source_database'), row.get('change_id'))])
        for ref in [*row.get('input_references', []), *row.get('result_references', []), *row.get('processing_references', [])]:
            linked |= reference_events(ref)
        # Vector jobs belong only to their exact description/event, never all
        # events extracted from the same source content.
        if row['task_kind'] != 'vector_index':
            for scope in row.get('coverage', []):
                for ref in scope.get('business_changes', []):
                    linked |= change_events[(ref['source_database'], ref['change_id'])]
        attempt_events[identity] = linked
    # A retry and its predecessor retain the same event association even if
    # an intermediate status contains no results yet.
    changed = True
    while changed:
        changed = False
        for identity, row in attempts.items():
            previous = row.get('previous_attempt_id')
            if previous in attempt_events:
                linked = attempt_events[identity] | attempt_events[previous]
                if linked != attempt_events[identity] or linked != attempt_events[previous]:
                    attempt_events[identity] = set(linked)
                    attempt_events[previous] = set(linked)
                    changed = True

    groups = {}
    event_groups = defaultdict(set)

    def change_group(key):
        group_id = f'change:{key[0]}:{key[1]}'
        if group_id not in groups:
            change = changes.get(key)
            groups[group_id] = {'object_type': 'processing_group', 'group_id': group_id,
                'change': change, 'events': [], 'records': [],
                'title': (change.get('title') or '业务变更') if change else '变更记录当前不可读取',
                'occurrence_time': {'start': {'value': change['recorded_at'], 'precision': 'datetime'}} if change else None,
                'submitted_at': '', 'record_sequence': 0}
        return group_id

    # The source identity is stable before extraction, after extraction and
    # across retries. Shared evidence does not merge distinct business changes.
    for row in attempts.values():
        if row.get('source_database') and row.get('change_id'):
            change_group((row['source_database'], row['change_id']))
    for identity, row in events.items():
        keys = {(ref['source_database'], ref['change_id']) for ref in row.get('evidence', [])}
        for key in keys:
            event_groups[identity].add(change_group(key))
        if not keys:
            key = f'event:{identity}'
            groups[key] = {'object_type': 'processing_group', 'group_id': key, 'change': None,
                'events': [], 'records': [], 'title': row['title'],
                'occurrence_time': row.get('occurrence_time'),
                'submitted_at': row['submitted_at'], 'record_sequence': row['record_sequence']}
            event_groups[identity].add(key)
        for key in event_groups[identity]:
            groups[key]['events'].append(row)
            groups[key]['record_sequence'] = max(groups[key]['record_sequence'], row['record_sequence'])
            groups[key]['submitted_at'] = max(groups[key]['submitted_at'], row['submitted_at'])

    attempt_groups = {}
    for identity, row in sorted(attempts.items(), key=lambda item: item[1]['record_sequence']):
        if row.get('source_database') and row.get('change_id'):
            keys = {change_group((row['source_database'], row['change_id']))}
        else:
            keys = set().union(*(event_groups[event_id] for event_id in attempt_events[identity]))
        if not keys:
            keys = attempt_groups.get(row.get('previous_attempt_id')) or {f'attempt:{identity}'}
            key = next(iter(keys))
            groups.setdefault(key, {'object_type': 'processing_group', 'group_id': key, 'change': None,
                'events': [], 'title': row['purpose'], 'records': [],
                'submitted_at': row['submitted_at'], 'record_sequence': row['record_sequence']})
        attempt_groups[identity] = keys
        for key in keys:
            groups[key]['records'].append(row)

    for kind in ('vector_binding',):
        for row in by_kind[kind].values():
            keys = set().union(*(
                event_groups[identity] for identity in reference_events(
                    {'object_type': kind, 'object_id': row[MEMORY_OBJECTS[kind][1]]})))
            for key in keys:
                groups[key]['records'].append(row)
    for group in groups.values():
        bindings = [r for r in group['records'] if r['object_type'] == 'vector_binding']
        for space_id in dict.fromkeys(r['space_id'] for r in bindings):
            if space_id in by_kind['vector_space']:
                group['records'].append(by_kind['vector_space'][space_id])
        records = group['records']
        records.sort(key=lambda row: (row['record_sequence'], row['object_type']))
        jobs = [row for row in records if row['object_type'] == 'processing_attempt']
        replaced = {row.get('previous_attempt_id') for row in jobs}
        current = [row for row in jobs if row['attempt_id'] not in replaced]
        if any(row['task_kind'] == 'event_formation' for row in current):
            # The formation attempt owns the outcome of its fixed stages.
            # Evidence-linked judgments remain readable history, not additional
            # requirements on a change that has since completed successfully.
            # Vector delivery has its own recovery and still affects readiness.
            current = [row for row in current if row['task_kind'] in
                       {'intake_review', 'event_formation', 'vector_index'}]
        states = [row.get('processing_status') for row in current]
        group['processing_status'] = next((state for state in ('failed', 'running', 'pending', 'cancelled') if state in states),
            'completed' if states and all(state == 'completed' for state in states) else 'unknown')
        group['event_count'] = len(group['events'])
        group['completed_tasks'] = sum(state == 'completed' for state in states)
        group['total_tasks'] = len(states)
        group['record_sequence'] = max([group['record_sequence'], *(row['record_sequence'] for row in records)])
        group['submitted_at'] = max([group['submitted_at'], *(row['submitted_at'] for row in records)])
    return sorted(groups.values(), key=lambda row: (-row['record_sequence'], row['group_id']))


def processing_scope(connection, access, cutoff, change_keys):
    """Select exact source dependencies before loading their object contents."""
    selected = defaultdict(set)
    if not change_keys:
        return selected
    keys = sorted(set(change_keys))
    values = ','.join('(?,?)' for _ in keys)
    sql = f"""WITH RECURSIVE requested(source_database,change_id) AS (VALUES {values}),
        events_in_scope(event_id) AS (
            SELECT DISTINCT e.event_id FROM event_evidence e JOIN commits c USING(commit_id)
            JOIN requested r ON r.source_database=e.source_database AND r.change_id=e.change_id
            WHERE e.account_id=? AND e.member_id=? AND c.sequence<=?),
        bindings_in_scope(binding_id,space_id) AS (
            SELECT v.binding_id,v.space_id FROM event_vectors v JOIN commits c USING(commit_id)
            WHERE v.account_id=? AND v.member_id=? AND c.sequence<=? AND v.event_id IN events_in_scope),
        eligible AS (
            SELECT p.attempt_id,p.previous_attempt_id,p.source_database,p.change_id,p.task_kind,
                   p.input_references_json,p.result_references_json,p.coverage_json
            FROM processing_attempts p JOIN commits c USING(commit_id)
            WHERE p.account_id=? AND p.member_id=? AND c.sequence<=?),
        seeds(attempt_id) AS (
            SELECT p.attempt_id FROM eligible p WHERE
            EXISTS(SELECT 1 FROM requested r WHERE r.source_database=p.source_database AND r.change_id=p.change_id)
            OR EXISTS(SELECT 1 FROM json_each(p.input_references_json) r WHERE
                (json_extract(r.value,'$.object_type')='event' AND json_extract(r.value,'$.object_id') IN events_in_scope)
                OR (json_extract(r.value,'$.object_type') IN ('vector_binding','vector_status') AND json_extract(r.value,'$.object_id') IN (SELECT binding_id FROM bindings_in_scope)))
            OR EXISTS(SELECT 1 FROM json_each(p.result_references_json) r WHERE
                (json_extract(r.value,'$.object_type')='event' AND json_extract(r.value,'$.object_id') IN events_in_scope)
                OR (json_extract(r.value,'$.object_type') IN ('vector_binding','vector_status') AND json_extract(r.value,'$.object_id') IN (SELECT binding_id FROM bindings_in_scope)))
            OR (p.task_kind!='vector_index' AND EXISTS(
                SELECT 1 FROM json_each(p.coverage_json) q, json_each(q.value,'$.business_changes') b
                JOIN requested r ON r.source_database=json_extract(b.value,'$.source_database') AND r.change_id=json_extract(b.value,'$.change_id')))),
        attempts_in_scope(attempt_id) AS (
            SELECT attempt_id FROM seeds UNION
            SELECT p.attempt_id FROM eligible p JOIN attempts_in_scope s ON p.previous_attempt_id=s.attempt_id UNION
            SELECT p.previous_attempt_id FROM eligible p JOIN attempts_in_scope s ON p.attempt_id=s.attempt_id WHERE p.previous_attempt_id IS NOT NULL)
        SELECT 'event',event_id FROM events_in_scope UNION ALL
        SELECT 'vector_binding',binding_id FROM bindings_in_scope UNION ALL
        SELECT 'vector_space',space_id FROM bindings_in_scope UNION ALL
        SELECT 'processing_attempt',attempt_id FROM attempts_in_scope"""
    scope = (access.account_id, access.member_id, cutoff)
    for kind, identity in connection.execute(sql, [*(part for key in keys for part in key), *scope, *scope, *scope]):
        selected[kind].add(identity)
    return selected


def read_processing_rows(repo, connection, access, cutoff, *, change_keys=None, summary=False, compact=False):
    if connection is None:
        return []
    decoded = []
    selected_ids = processing_scope(connection, access, cutoff, change_keys) if change_keys is not None else None
    for kind in KINDS:
        if (summary and kind in {'vector_space'}) or (compact and kind == 'vector_space'):
            continue
        table, primary = MEMORY_OBJECTS[kind]
        ids = sorted(selected_ids[kind]) if selected_ids is not None else None
        if ids == []:
            continue
        where = '' if ids is None else ' AND o.' + primary + ' IN (' + ','.join('?' for _ in ids) + ')'
        columns = 'o.*'
        if (summary or compact) and kind == 'event':
            columns = 'o.event_id,o.account_id,o.member_id,o.commit_id,o.title,o.occurrence_time_json'
        decoded.extend({**repo._decode(dict(raw)), 'object_type': kind} for raw in connection.execute(
            f'SELECT {columns}, c.sequence AS record_sequence, c.submitted_at FROM {table} o JOIN commits c USING(commit_id) '
            'WHERE o.account_id=? AND o.member_id=? AND c.sequence<=?' + where, (access.account_id, access.member_id, cutoff, *(ids or []))))
    if change_keys is not None:
        # Select the current page's dependency graph before expensive permission
        # checks and execution projections. Nothing in this preliminary graph is
        # returned until the ordinary live visibility checks below succeed.
        events = {row['event_id']: row for row in decoded if row['object_type'] == 'event'}
        for raw in connection.execute('SELECT e.event_id,e.source_database,e.change_id,e.field_path FROM event_evidence e '
                'JOIN commits c USING(commit_id) WHERE e.account_id=? AND e.member_id=? AND c.sequence<=? AND e.event_id IN (' + ','.join('?' for _ in events) + ')',
                (access.account_id, access.member_id, cutoff, *events)):
            if raw['event_id'] in events:
                events[raw['event_id']].setdefault('evidence', []).append(dict(raw))
        wanted = {f'change:{database}:{identity}' for database, identity in change_keys}
        selected = {}
        for group in group_processing(decoded, {}):
            if group['group_id'] in wanted:
                for row in [*group['events'], *group['records']]:
                    selected[(row['object_type'], row[MEMORY_OBJECTS[row['object_type']][1]])] = row
        decoded = list(selected.values())
        for row in decoded:
            row.pop('processing_references', None)
    # List summaries need current task statuses and authorized event counts;
    # execution entries, event associations and vector details belong to detail reads.
    rows = [repo._project(connection, access, row, cutoff, include_execution_entries=not (summary or compact)) if not (summary or compact) or row['object_type'] == 'processing_attempt'
        else row for row in decoded if repo._visible(connection, access, row)]
    return rows


class MemoryProcessingCatalogRepository:
    def __init__(self, repository):
        self.repository = repository

    def read_snapshot(self, actor, member, query, *, can_append, change_keys=None, summary=False, compact=False):
        from backend.app.core.pagination import seek_cursor, seek_position
        from backend.app.repositories.memory.transaction import memory_operation
        repo = self.repository
        with memory_operation('processing_summary' if summary else 'processing_catalog'), repo._transaction(actor, member) as (access, connection):
            scope = ['processing-changes', access.account_id, member, access.permission,
                access.grant_updated_at.isoformat() if access.grant_updated_at else 'owner',
                query.model_dump(mode='json', exclude={'cursor', 'record_cutoff', 'limit'})]
            try:
                position = seek_position(query.cursor, scope=scope, size=3)
                cutoff = repo._cutoff(connection, access, int(position[0]) if position else query.record_cutoff)
                last = (-int(position[1]), position[2]) if position else None
            except (TypeError, ValueError):
                raise SerenitaError('invalid_input', 'MEMORY_CURSOR_SCOPE', '分页游标无效。')
            if position and query.record_cutoff is not None and query.record_cutoff != cutoff:
                raise SerenitaError('invalid_input', 'MEMORY_CURSOR_SCOPE', '分页游标不属于指定记录截点。')
            rows = read_processing_rows(repo, connection, access, cutoff, change_keys=change_keys, summary=summary, compact=compact)
            attempts = [row for row in rows if row['object_type'] == 'processing_attempt']
            live = query.view != 'historical_saved' and can_append and cutoff == repo._cutoff(connection, access)
            eligibility = connection.execute(
                "SELECT previous_attempt_id,task_kind,source_database,change_id,processing_status "
                "FROM processing_attempts WHERE account_id=? AND member_id=?",
                (access.account_id, member)).fetchall() if live and not summary and connection is not None else []
            successors = {row['previous_attempt_id'] for row in eligibility}
            completed_changes = {(row['source_database'], row['change_id']) for row in eligibility
                if row['task_kind'] == 'event_formation' and row['processing_status'] == 'completed'}
            from backend.app.repositories.memory.sources.evidence import read_change, read_change_title
            keys = {(row['source_database'], row['change_id']) for row in attempts
                if row.get('source_database') and row.get('change_id')}
            keys.update((ref['source_database'], ref['change_id']) for row in rows
                if row['object_type'] == 'event' for ref in row.get('evidence', []))
            changes = {}
            for database, change_id in keys:
                try:
                    reader = read_change_title if summary or compact else read_change
                    change = reader(repo, access, {'source_database': database, 'change_id': change_id}, connection)
                except SerenitaError as error:
                    if error.kind in {'missing', 'forbidden'}:
                        continue
                    raise
                title = change.get('title') or next((field['after_value'] for field in change['fields']
                    if field['field_path'] in {'/report_name', '/title', '/member_name'}
                    and field['after_exists'] and isinstance(field['after_value'], str) and field['after_value']), None)
                title = title or change.get('context', {}).get('title') or change.get('context', {}).get('original_filename')
                changes[(database, change_id)] = {**{key: change[key] for key in
                    ('source_database', 'change_id', 'resource_type', 'resource_id', 'operation_kind', 'recorded_at', 'fields')},
                    'title': title}
            groups = group_processing(rows, changes)
            if change_keys is not None:
                group_ids = {f'change:{database}:{identity}' for database, identity in change_keys}
                groups = [row for row in groups if row['group_id'] in group_ids]
            # Filtering and pagination apply to complete change groups. Child
            # records cannot split a change across pages or hide its progress.
            groups = [row for row in groups if repo._matches(connection, access,
                {**row, **{key: value for key, value in (row['records'][0] if row['records'] else row['events'][0]).items()
                    if key not in {'title', 'occurrence_time'}}}, query)]
            remaining = [row for row in groups if last is None or (-row['record_sequence'], row['group_id']) > last]
            selected = remaining[:query.limit]
            following = seek_cursor(scope, [str(cutoff), str(selected[-1]['record_sequence']), selected[-1]['group_id']]) if len(remaining) > query.limit else None
            # Work checkpoints and their payload files are read after releasing
            # the account database lock. Each reader enforces its own live scope.
            result = repo._observation(access, query, cutoff, selected, total=len(groups), next_cursor=following)
        return {'result': result, 'rows': rows, 'selected': selected, 'live': live,
            'successors': successors, 'completed_changes': completed_changes}
