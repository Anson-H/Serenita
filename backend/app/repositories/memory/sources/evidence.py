"""Resolve event evidence from the business ledger inside the current scope."""
from backend.app.repositories.business_source_generation import business_generation
import json
from copy import deepcopy
from backend.app.core.errors import SerenitaError
from backend.app.schemas.memory.evidence import ChangeReference, source_key
from backend.app.repositories.business_change_repository import read_change_fields
from backend.app.domain.memory.sources import SOURCE_REGISTRATIONS


def read_change(repo, access, reference, connection=None, *, include_subject_names=True, _check_only=False):
    ref = ChangeReference.model_validate(reference).model_dump()
    from backend.app.repositories.memory.reading.prepared_reads import prepared_reads
    from backend.app.repositories.memory.reading.read_cache import MAX_CHECKED_SOURCES
    from backend.app.repositories.memory.reading.read_cache import access_key
    prepared = prepared_reads(repo, access)
    key = (*access_key(access), ref['source_database'], ref['change_id'], ref['field_path'])
    from backend.app.repositories.memory.sources.source_access import MemorySourceAccess
    from backend.app.repositories.memory.sources.restrictions import source_restrictions_allow
    reader = MemorySourceAccess(repo.members, repo.paths)
    try:
        cached = prepared.changes.get(key) if prepared is not None else None
        if cached is not None:
            change, source = cached
            with reader._database(access.account_id, ref['source_database']) as db:
                # The ledger body is immutable. Existence, source generation and
                # permission remain live checks, including on cache hits.
                if db.execute('SELECT 1 FROM business_changes WHERE change_id=? AND change_sequence=?',
                        (ref['change_id'], change['change_sequence'])).fetchone() is None:
                    raise LookupError()
                if ref['field_path'] and db.execute('SELECT 1 FROM business_change_fields WHERE change_id=? AND field_path=?',
                        (ref['change_id'], ref['field_path'])).fetchone() is None:
                    raise LookupError()
                if include_subject_names and 'subject_names' not in change:
                    change['subject_names'] = input_subject_names(db, change, change['fields'])
            callback = repo.source_access_check or reader.check
            if not callback(access, source) or connection is not None and not source_restrictions_allow(connection, access, source['source_id']):
                raise LookupError()
            _remember_change(connection, access, ref)
            if _check_only:
                return None
            result = deepcopy(change)
            if not include_subject_names:
                result.pop('subject_names', None)
            return result
        with reader._database(access.account_id, ref['source_database']) as db:
            row = db.execute("SELECT * FROM business_changes WHERE change_id=? AND "
                "((scope_kind='member' AND member_id=?) OR scope_kind='account')",
                (ref['change_id'], access.member_id)).fetchone()
            if row is None:
                raise LookupError()
            change = dict(row)
            registration = SOURCE_REGISTRATIONS.get(change['resource_type'])
            if registration is None or registration.database != ref['source_database']:
                raise LookupError()
            # Visibility checks need existence and permissions, not the full
            # before/after values of every field in a large medical report.
            fields = [] if _check_only else read_change_fields(db, ref['change_id'])
            if _check_only and ref['field_path']:
                if db.execute('SELECT 1 FROM business_change_fields WHERE change_id=? AND field_path=?',
                        (ref['change_id'], ref['field_path'])).fetchone() is None:
                    raise LookupError()
            elif ref['field_path']:
                fields = [field for field in fields if field['field_path'] == ref['field_path']]
                if not fields:
                    raise LookupError()
            generation = business_generation(db, change['resource_type'], change['resource_id'],
                change['member_id'], at_sequence=change['change_sequence'])
            if include_subject_names:
                change['subject_names'] = input_subject_names(db, change, fields)
        from backend.app.schemas.memory.source_identity import memory_source_id
        source = dict(source_account_id=access.account_id, source_database=ref['source_database'],
            resource_type=change['resource_type'], resource_id=change['resource_id'], source_generation=generation,
            source_member_id=change['member_id'], source_category=next(iter(registration.categories)),
            account_id=access.account_id, member_id=access.member_id)
        source['source_id'] = memory_source_id(access.member_id, **{k: source[k] for k in
            ('source_account_id','source_database','resource_type','resource_id','source_generation')})
        callback = repo.source_access_check or reader.check
        if not callback(access, source) or connection is not None and not source_restrictions_allow(connection, access, source['source_id']):
            raise LookupError()
        if _check_only:
            _remember_change(connection, access, ref)
            return None
        change['context'] = json.loads(change.pop('context_json'))
        change.update(ref, fields=fields, source_category=source['source_category'])
        if prepared is not None:
            prepared.save(prepared.changes, key, (deepcopy(change), source), MAX_CHECKED_SOURCES)
        _remember_change(connection, access, ref)
        return None if _check_only else change
    except (FileNotFoundError, LookupError) as exc:
        raise SerenitaError('missing', 'MEMORY_EVIDENCE_UNAVAILABLE', '依据变更或字段不存在，或当前没有读取权限。') from exc


def _remember_change(connection, access, ref):
    from backend.app.repositories.memory.reading.read_cache import current_read_cache, MAX_CHECKED_SOURCES
    cache = current_read_cache(connection, access)
    if cache is not None:
        if len(cache.checked_changes) >= MAX_CHECKED_SOURCES and source_key(ref) not in cache.checked_changes:
            raise SerenitaError('resource_limit', 'MEMORY_EVIDENCE_BUDGET', '依据引用超过读取预算。')
        cache.checked_changes[source_key(ref)] = ref


def check_change(repo, access, reference, connection=None):
    """Recheck a source without copying its already prepared body."""
    read_change(repo, access, reference, connection, include_subject_names=False, _check_only=True)


def read_change_title(repo, access, reference, connection):
    """Read only the ledger header and title fields after checking live access."""
    check_change(repo, access, reference, connection)
    from backend.app.repositories.memory.sources.source_access import MemorySourceAccess
    reader = MemorySourceAccess(repo.members, repo.paths)
    with reader._database(access.account_id, reference['source_database']) as db:
        row = db.execute('SELECT change_id,resource_type,resource_id,operation_kind,recorded_at,context_json '
            'FROM business_changes WHERE change_id=?', (reference['change_id'],)).fetchone()
        if row is None:
            raise SerenitaError('missing', 'MEMORY_EVIDENCE_UNAVAILABLE', '依据变更当前不可读取。')
        fields = db.execute("SELECT after_json FROM business_change_fields WHERE change_id=? "
            "AND field_path IN ('/report_name','/title','/member_name') AND after_json IS NOT NULL ORDER BY field_path",
            (reference['change_id'],)).fetchall()
    values = [json.loads(field['after_json']) for field in fields if field['after_json'] is not None]
    change = dict(row)
    context = json.loads(change.pop('context_json'))
    title = next((value for value in values if isinstance(value, str) and value), None)
    return {**change, 'source_database': reference['source_database'], 'fields': [],
        'title': title or context.get('title') or context.get('original_filename')}




def change_references(repo, connection, access, row):
    """Follow declared object dependencies; resolve direct business references."""
    from backend.app.repositories.memory.reading.object_projection import stored_references
    from backend.app.domain.memory.references import object_reference, reference_key
    if row is None or connection is None:
        return []
    pending, seen, result = [row], set(), {}
    while pending:
        current = pending.pop()
        key = reference_key(object_reference(current))
        if key in seen:
            continue
        seen.add(key)
        if current['object_type'] == 'memory_execution_entry':
            from backend.app.repositories.memory.processing.execution import execution_visible
            if not execution_visible(repo, connection, access, current):
                raise SerenitaError('missing', 'MEMORY_EVIDENCE_UNAVAILABLE', '模型记录依据当前不可读取。')
        if len(seen) > 20000:
            raise SerenitaError('resource_limit','MEMORY_EVIDENCE_BUDGET','依据引用超过本次读取预算。')
        for coverage in [*current.get('coverage', []), *current.get('counterevidence_coverage', [])]:
            if isinstance(coverage,dict):
                for ref in coverage.get('business_changes', []):
                    result[source_key(ref)]=ref
        if current['object_type'] == 'episode_revision':
            from backend.app.repositories.memory.reading.revision_input import revision_input, revision_sources
            data = revision_input(repo, connection, access, current)
            for ref in revision_sources(data):
                result[source_key(ref)] = ref
            for value in data.get('objects', []):
                ref = object_reference(value)
                target = repo._record(connection, access, ref['object_type'], ref['object_id'],
                    version=ref.get('version'), item_id=ref.get('item_id'), cutoff=data['record_cutoff'])
                if target is not None:
                    pending.append(target)
        if current['object_type'] == 'episode':
            # The membership saved with creation identifies the description's basis.
            initial = connection.execute(
                'SELECT event_id FROM event_episode WHERE account_id=? AND member_id=? AND episode_id=? AND commit_id=?',
                (access.account_id, access.member_id, current['episode_id'], current['commit_id']))
            for membership in initial:
                event = repo._record(connection, access, 'event', membership['event_id'])
                if event is not None:
                    pending.append(event)
        if current['object_type'] == 'event':
            for ref in event_references(connection, access, current['event_id']):
                result[source_key(ref)] = ref
            continue
        if current['object_type'] == 'processing_attempt' and current.get('change_id') and current.get('task_kind') != 'intake_review':
            ref = {key: current[key] for key in ('source_database','change_id')}
            ref['field_path'] = ''
            result[source_key(ref)] = ref
        references = [ref for ref, _ in stored_references(current)]
        for ref in references:
            target=repo._record(connection,access,ref['object_type'],ref['object_id'],version=ref.get('version'),item_id=ref.get('item_id'),include_payload=False)
            if target is not None:
                pending.append(target)
    return list(result.values())


def change_source(change):
    """Join a change's health fields into one traceable text input."""
    from backend.app.repositories.memory.reading.prepared_reads import prepared_reads
    from backend.app.repositories.memory.reading.read_cache import MAX_CHECKED_SOURCES
    from backend.app.core.values import strict_digest as digest
    prepared = prepared_reads()
    key = digest(change)
    if prepared is not None and key in prepared.source_texts:
        return deepcopy(prepared.source_texts[key])
    result = _change_source(change)
    if prepared is not None:
        prepared.save(prepared.source_texts, key, deepcopy(result), MAX_CHECKED_SOURCES)
    return result


def _change_source(change):
    from backend.app.domain.memory.source_markdown import source_document, source_title
    from backend.app.domain.memory.change_scope import memory_change_fields
    selected = {**change, 'fields': memory_change_fields(change['resource_type'], change['fields'])}
    reference={key: change[key] for key in ('source_database','change_id','field_path')}
    context_keys = ('member_name', 'recorded_on', 'report_time', 'starts_at', 'ends_at')
    document_context = {key: value for key, value in change.get('context', {}).items() if key in context_keys}
    document_context.update({field['field_path'][1:]: field['after_value'] for field in selected['fields']
        if field['field_path'][1:] in context_keys and field['after_exists']})
    document = source_document(selected)
    document_context.update(resource_type=change['resource_type'], operation_kind=change['operation_kind'],
                            source_title=source_title(selected), recorded_at=change['recorded_at'])
    return {'source_key':source_key(reference),'reference':reference,'content_text':document['text'],
        'content_units': document['units'],
        'title': source_title(selected), 'document_context': document_context,
        **{key:change[key] for key in ('resource_type','resource_id','recorded_at','operation_kind','source_category')}}


def input_subject_names(db, change, fields):
    """Read names and units within this lifecycle at the exact change cutoff."""
    paths = {field['field_path'].rsplit('/', 1)[0] + '/item_name_zh' for field in fields
        if field['field_path'].startswith('/lab_test_results/')}
    for field in fields:
        path = field['field_path']
        prefix = path.rsplit('/', 1)[0]
        for root, key in (('/data/foods/', 'name'), ('/data/foods/', 'amount_unit'), ('/data/stages/', 'stage'), ('/data/metrics/', 'unit')):
            if path.startswith(root):
                paths.add(prefix + '/' + key)
    names = {}
    current = {field['field_path']: field for field in fields}
    for path in sorted(paths):
        if path in current:
            if current[path]['after_exists']:
                names[path] = current[path]['after_value']
            continue
        row = db.execute('SELECT f.after_json FROM business_change_fields f JOIN business_changes c USING(change_id) '
            'WHERE c.resource_type=? AND c.resource_id=? AND c.member_id IS ? AND c.scope_kind=? '
            'AND f.field_path=? AND c.change_sequence<=? AND c.change_sequence>='
            '(SELECT MAX(change_sequence) FROM business_changes WHERE resource_type=? AND resource_id=? '
            'AND member_id IS ? AND scope_kind=? AND operation_kind=? AND change_sequence<=?) '
            'ORDER BY c.change_sequence DESC LIMIT 1',
            (change['resource_type'], change['resource_id'], change['member_id'], change['scope_kind'], path,
             change['change_sequence'], change['resource_type'], change['resource_id'], change['member_id'],
             change['scope_kind'], 'create', change['change_sequence'])).fetchone()
        if row and row['after_json'] is not None:
            names[path] = json.loads(row['after_json'])
    return names


def evidence_categories(repo,db,access,row):
    return {read_change(repo,access,ref,db)['source_category'] for ref in change_references(repo,db,access,row)}



from backend.app.repositories.memory.facts.event_evidence import event_references
