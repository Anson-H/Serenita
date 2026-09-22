"""Read the existing member business ledgers without creating storage."""
import json

from backend.app.core.pagination import seek_cursor, seek_position
from backend.app.repositories.business_change_repository import read_change_fields


class MemoryChangeRepository:
    @classmethod
    def for_memory(cls, repository):
        from backend.app.repositories.memory.sources.source_access import MemorySourceAccess
        from backend.app.domain.memory.sources import SOURCE_REGISTRATIONS, BUSINESS_SOURCE_DATABASES
        sources = MemorySourceAccess(repository.members, repository.paths)
        return cls(sources._database, SOURCE_REGISTRATIONS, BUSINESS_SOURCE_DATABASES)

    def __init__(self, database, registrations, databases):
        self.database, self.registrations, self.databases = database, registrations, databases

    def catalog(self, access, cursor=None, limit=30):
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError('每页数量须为 1 至 100。')
        scope = [access.actor_account_id, access.account_id, access.member_id,
                 access.permission, str(access.grant_updated_at), 'business_changes']
        position = seek_position(cursor, scope=scope, size=3)
        if position and (position[1] not in self.databases or not position[2].isdigit() or not 0 < int(position[2]) < 2**63):
            raise ValueError('分页范围无效。')
        rows = []
        for database in self.databases:
            kinds = [kind for kind, spec in self.registrations.items()
                     if spec.database == database and spec.scope == 'member']
            if not kinds:
                continue
            try:
                with self.database(access.account_id, database) as conn:
                    if not conn.execute("SELECT 1 FROM sqlite_master WHERE name='business_changes' AND type='table'").fetchone():
                        continue
                    sql = "SELECT change_id, resource_type, resource_id, operation_kind, recorded_at, change_sequence, memory_status FROM business_changes WHERE scope_kind='member' AND member_id=? AND resource_type IN (" + ','.join('?' for _ in kinds) + ')'
                    params = [access.member_id, *kinds]
                    if position:
                        sql += ' AND (recorded_at, ?, change_sequence) < (?, ?, ?)'
                        params.extend([database, position[0], position[1], int(position[2])])
                    sql += ' ORDER BY recorded_at DESC, change_sequence DESC LIMIT ?'
                    params.append(limit + 1)
                    for row in conn.execute(sql, params):
                        rows.append({**dict(row), 'source_database': database})
            except FileNotFoundError:
                continue
        rows.sort(key=lambda row: (row['recorded_at'], row['source_database'], row['change_sequence']), reverse=True)
        page = rows[:limit]
        last = page[-1] if page else None
        return {'changes': page, 'next_cursor': seek_cursor(scope, [last['recorded_at'], last['source_database'], str(last['change_sequence'])]) if len(rows) > limit else None}

    def summaries(self, access, references):
        from collections import defaultdict
        groups = defaultdict(set)
        for reference in references:
            groups[reference['source_database']].add(reference['change_id'])
        rows = []
        for database, identities in groups.items():
            if database not in self.databases:
                raise LookupError()
            try:
                with self.database(access.account_id, database) as db:
                    marks = ','.join('?' for _ in identities)
                    for raw in db.execute('SELECT change_id,resource_type,resource_id,operation_kind,recorded_at,memory_status '
                            "FROM business_changes WHERE scope_kind='member' AND member_id=? AND change_id IN (" + marks + ')',
                            (access.member_id, *sorted(identities))):
                        spec = self.registrations.get(raw['resource_type'])
                        if spec is not None and spec.database == database and spec.scope == 'member':
                            rows.append({**dict(raw), 'source_database': database})
            except FileNotFoundError:
                continue
        return rows

    def detail(self, access, database, change_id, *, content=True):
        if database not in self.databases:
            raise LookupError()
        with self.database(access.account_id, database) as conn:
            row = conn.execute("SELECT * FROM business_changes WHERE change_id=? AND scope_kind='member' AND member_id=?", (change_id, access.member_id)).fetchone()
            if row is None:
                raise LookupError()
            change = dict(row)
            spec = self.registrations.get(change['resource_type'])
            if spec is None or spec.database != database or spec.scope != 'member':
                raise LookupError()
            change['context'] = json.loads(change.pop('context_json'))
            change['source_database'] = database
            change['fields'], change['subject_names'], change['targets'] = [], {}, []
            if not content:
                return change
            change['fields'] = read_change_fields(conn, change_id)
            from backend.app.repositories.memory.sources.evidence import input_subject_names
            change['subject_names'] = input_subject_names(conn, change, change['fields'])
            change['subject_names'].update(deleted_subject_names(conn, change))
            change['targets'] = self._targets(conn, access, change, spec)
            return change

    @staticmethod
    def _targets(conn, access, change, spec):
        # Resolve live parent identifiers from business data, not historical field values.
        row = conn.execute(
            f'SELECT * FROM {spec.table} WHERE {spec.primary_key}=? AND member_id=?',
            (change['resource_id'], access.member_id),
        ).fetchone()
        if row is None:
            return []
        kind = change['resource_type']
        if kind == 'report_source':
            return [{'resource_type': 'report', 'resource_id': link['report_id']} for link in conn.execute(
                'SELECT report_id FROM report_source_links WHERE resource_id=? AND member_id=? ORDER BY report_id',
                (change['resource_id'], access.member_id),
            )]
        if kind == 'body_file':
            return [{'resource_type': 'body_record', 'resource_id': row['record_id']}]
        target = {'resource_type': kind, 'resource_id': change['resource_id']}
        if kind == 'medication_batch':
            target['medication_id'] = row['medication_id']
        return [target]


def deleted_subject_names(conn, change):
    """Read deleted subject names at the preceding ledger cutoff for the detail page."""
    values = {}
    for field in change['fields']:
        if field['after_exists'] or field['field_path'].rsplit('/', 1)[-1] not in {'item_name_zh', 'name', 'stage'}:
            continue
        row = conn.execute(
            'SELECT f.after_json FROM business_change_fields f JOIN business_changes c USING(change_id) '
            'WHERE c.resource_type=? AND c.resource_id=? AND c.member_id IS ? AND c.scope_kind=? '
            'AND f.field_path=? AND c.change_sequence<? AND c.change_sequence>='
            '(SELECT MAX(change_sequence) FROM business_changes WHERE resource_type=? AND resource_id=? '
            'AND member_id IS ? AND scope_kind=? AND operation_kind=\'create\' AND change_sequence<?) '
            'ORDER BY c.change_sequence DESC LIMIT 1',
            (change['resource_type'], change['resource_id'], change['member_id'], change['scope_kind'],
             field['field_path'], change['change_sequence'], change['resource_type'], change['resource_id'],
             change['member_id'], change['scope_kind'], change['change_sequence']),
        ).fetchone()
        if row and row['after_json'] is not None:
            values[field['field_path']] = json.loads(row['after_json'])
    return values
