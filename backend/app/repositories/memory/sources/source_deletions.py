"""Durable deletion effects using existing business command receipts.

The source deletion and its delivery registration share one business database
transaction. Restrictions commit separately, then a completion receipt is
appended. A failure after business commit is reported as pending, never as an
atomic rollback across independent WAL databases.
"""
from dataclasses import dataclass, field
import json
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from backend.app.core.errors import SerenitaError
from backend.app.storage.sqlite import connect, connect_read_only


DOMAIN = 'memory_source_deletion'
from backend.app.storage.source_paths import SOURCE_DATABASES, registered_source_path, safe_existing_file
from backend.app.repositories.business_source_generation import business_generation


def identity(*values):
    return str(uuid5(NAMESPACE_URL, json.dumps(['serenita-source-deletion', *values], separators=(',', ':'))))


@dataclass(frozen=True)
class DeletionJournal:
    paths: object
    source_account_id: str
    source_database: str
    schema_alias: str


    def change_recorded(self, connection, record):
        journal, schema_alias = self, self.schema_alias
        if record['operation_kind'] != 'delete':
            return
        from backend.app.domain.memory.sources import SOURCE_REGISTRATIONS
        from backend.app.repositories.business_operation_repository import begin_operation, finish_operation
        registration = SOURCE_REGISTRATIONS.get(record['resource_type'])
        if registration is None:
            return
        if registration.database != journal.source_database:
            raise ValueError('Deleted resource is not registered in its actual source database')
        creation = connection.execute(f'SELECT change_id FROM "{schema_alias}".business_changes '
            'WHERE resource_type=? AND resource_id=? AND member_id IS ? AND operation_kind=\'create\' '
            'AND change_sequence<=? ORDER BY change_sequence DESC LIMIT 1',
            (record['resource_type'], record['resource_id'], record['member_id'], record['change_sequence'])).fetchone()
        # Without a creation identity there cannot be a valid ingested Source.
        if creation is None:
            return
        operation = identity(journal.source_account_id, journal.source_database, record['change_id'])
        command = {'domain': DOMAIN, 'action': 'deliver', 'parent_operation_id': record['operation_id'],
            'source_account_id': journal.source_account_id, 'source_database': journal.source_database,
            'source_member_id': record['member_id'], 'resource_type': record['resource_type'],
            'resource_id': record['resource_id'], 'source_generation': 'change:' + creation['change_id'],
            'change_id': record['change_id'], 'effective_at': record['recorded_at'],
            'completion_operation_id': identity(operation, 'completed')}
        if begin_operation(connection, record['actor_account_id'], operation, command, schema_alias=schema_alias) is None:
            finish_operation(connection, record['actor_account_id'], operation, {'delivery': 'registered'}, schema_alias=schema_alias)
        _schedule(connection, journal, operation, record['operation_id'])


    def operation_replayed(self, connection, operation_id):
        journal, schema_alias = self, self.schema_alias
        rows = connection.execute(f'SELECT operation_id FROM "{schema_alias}".business_operations '
            "WHERE json_extract(original_command_json,'$.domain')=? "
            "AND json_extract(original_command_json,'$.action')='deliver' "
            "AND json_extract(original_command_json,'$.parent_operation_id')=?", (DOMAIN, operation_id)).fetchall()
        for row in rows:
            _schedule(connection, journal, row['operation_id'], operation_id)

def bind_deletion_journal(connection, paths, source_account_id, source_database, *, schema_alias='main'):
    """Bind only an explicitly registered actual business connection."""
    from backend.app.repositories.business_operation_repository import transaction_schema
    from backend.app.schemas.memory.values import canonical_uuid
    canonical_uuid(source_account_id)
    transaction_schema(connection, schema_alias)
    if source_database not in SOURCE_DATABASES:
        raise ValueError('Unregistered deletion source database')
    registered = registered_source_path(paths, source_account_id, source_database)
    if not safe_existing_file(registered, paths.root):
        raise ValueError('Deletion source database is not a safe existing file')
    expected = registered.resolve()
    actual = next((Path(row['file']).resolve() for row in connection.execute('PRAGMA database_list')
                   if row['name'] == schema_alias and row['file']), None)
    if actual != expected:
        raise ValueError('Deletion journal does not belong to the declared source account')
    from backend.app.repositories.business_operation_repository import bind_operation_effects
    bind_operation_effects(connection, DeletionJournal(paths, source_account_id, source_database, schema_alias),
                           schema_alias=schema_alias)


def _schedule(connection, journal, delivery_id, parent_operation_id):
    def complete():
        try:
            complete_deletion(journal.paths, journal.source_account_id, journal.source_database, delivery_id)
        except Exception as error:
            raise SerenitaError('conflict', 'BUSINESS_COMMITTED_MEMORY_RESTRICTION_PENDING',
                '业务删除已提交，原件读取已受限；记忆访问限制记录尚待完成，请使用原操作标识重试。',
                details={'business_committed': True, 'operation_id': parent_operation_id,
                         'restriction_delivery_id': delivery_id, 'cause_code': error.code if isinstance(error, SerenitaError) else type(error).__name__}) from error
    connection.after_commit(('memory_source_deletion', delivery_id), complete)


def _read_delivery(paths, source_account, database, delivery_id):
    path = registered_source_path(paths, source_account, database)
    if not safe_existing_file(path, paths.root):
        raise ValueError('Deletion source database is unavailable')
    with connect_read_only(path) as db:
        row = db.execute('SELECT o.*,r.result_json FROM business_operations o JOIN business_operation_results r USING(operation_id) '
            'WHERE o.operation_id=?', (delivery_id,)).fetchone()
        if row is None:
            raise ValueError('No committed deletion delivery exists')
        command = json.loads(row['original_command_json'])
        if (command.get('domain'), command.get('action'), command.get('source_account_id'), command.get('source_database')) != (DOMAIN, 'deliver', source_account, database):
            raise ValueError('Deletion receipt scope differs')
        change = db.execute("SELECT * FROM business_changes WHERE change_id=? AND operation_kind='delete'", (command['change_id'],)).fetchone()
        if change is None or any(change[key] != command[key] for key in ('resource_type', 'resource_id')) or change['operation_id'] != command['parent_operation_id'] or change['actor_account_id'] != row['actor_account_id']:
            raise ValueError('Deletion receipt lacks its actual committed business change')
        generation = business_generation(db, command['resource_type'], command['resource_id'],
            command['source_member_id'], at_sequence=change['change_sequence'])
        if generation != command['source_generation'] or change['member_id'] != command['source_member_id'] or command['effective_at'] != change['recorded_at']:
            raise ValueError('Deletion receipt generation or original scope differs')
        if delivery_id != identity(source_account, database, change['change_id']) or command['completion_operation_id'] != identity(delivery_id, 'completed'):
            raise ValueError('Deletion delivery identity differs from its actual change')
        completed = db.execute('SELECT o.actor_account_id,o.original_command_json,r.result_json FROM business_operations o '
            'JOIN business_operation_results r USING(operation_id) WHERE o.operation_id=?', (command['completion_operation_id'],)).fetchone()
        if completed and (completed['actor_account_id'] != row['actor_account_id']
                or json.loads(completed['original_command_json']) != {'domain': DOMAIN, 'action': 'confirm', 'delivery_id': delivery_id}
                or json.loads(completed['result_json']) != {'restriction_delivery_confirmed': True}):
            raise ValueError('Deletion completion receipt differs')
        return path, dict(row), command, bool(completed)


def complete_deletion(paths, source_account, database, delivery_id):
    from backend.app.repositories.members.authorization_repository import MemberAuthorizationRepository
    from backend.app.repositories.memory.sources.restrictions import append_restriction_on_connection
    from backend.app.repositories.business_operation_repository import begin_operation, finish_operation
    from backend.app.schemas.memory.append import AccessRestrictionInput, stable_memory_id
    from backend.app.storage.memory.database import MEMORY_DATABASE_SCHEMA
    path, receipt, command, completed = _read_delivery(paths, source_account, database, delivery_id)
    if completed:
        return {'delivery_id': delivery_id, 'completed': True, 'replayed': True}
    authorization = MemberAuthorizationRepository(paths)
    matched = 0
    with authorization.read() as auth:
        accounts = [row[0] for row in auth.execute('SELECT account_id FROM accounts ORDER BY account_id')]
        if source_account not in accounts or receipt['actor_account_id'] not in accounts:
            raise ValueError('The committed deletion account is unavailable')
        for owner in accounts:
            memory_path = registered_source_path(paths, owner, 'memory.db')
            if memory_path.exists():
                if not safe_existing_file(memory_path, paths.root):
                    raise ValueError('Registered memory database is not a safe existing file')
            if not MEMORY_DATABASE_SCHEMA.validate_existing(memory_path):
                continue
            with connect(memory_path) as db:
                db.execute('BEGIN IMMEDIATE')
                # Evidence and attempts carry the business reference directly.
                if owner != source_account:
                    continue
                from backend.app.schemas.memory.source_identity import memory_source_id
                with connect_read_only(path) as business:
                    changes = {row[0] for row in business.execute(
                        "SELECT change_id FROM business_changes WHERE resource_type=? AND resource_id=? AND member_id IS ?",
                        (command['resource_type'], command['resource_id'], command['source_member_id']))}
                references = db.execute("SELECT member_id,change_id FROM event_evidence WHERE account_id=? AND source_database=? "
                    "UNION SELECT member_id,change_id FROM processing_attempts WHERE account_id=? AND source_database=?",
                    (owner, database, owner, database))
                affected = {row['member_id'] for row in references if row['change_id'] in changes}
                sources = [{'member_id': member, 'source_id': memory_source_id(member, source_account_id=source_account,
                    source_database=database, resource_type=command['resource_type'], resource_id=command['resource_id'],
                    source_generation=command['source_generation'])} for member in sorted(affected)]
                for source in sources:
                    existing = db.execute("SELECT 1 FROM access_restrictions WHERE source_id=? AND restriction_kind='source_deleted'", (source['source_id'],)).fetchone()
                    if existing:
                        continue
                    member, source_id = source['member_id'], source['source_id']
                    operation = stable_memory_id(member, 'source-restriction', 'source_deleted', source_id)
                    restriction = AccessRestrictionInput(restriction_id=stable_memory_id(member, operation, 'access_restriction', source_id),
                        source_id=source_id, trigger_resource_type=command['resource_type'], trigger_resource_id=command['resource_id'],
                        restriction_kind='source_deleted', reason='原业务来源已删除。', effective_at=command['effective_at'])
                    append_restriction_on_connection(db, 'main', owner, member, receipt['actor_account_id'], restriction, operation)
                    matched += 1
        with connect(path) as db:
            db.execute('BEGIN IMMEDIATE')
            operation = command['completion_operation_id']
            value = {'domain': DOMAIN, 'action': 'confirm', 'delivery_id': delivery_id}
            if begin_operation(db, receipt['actor_account_id'], operation, value) is None:
                finish_operation(db, receipt['actor_account_id'], operation, {'restriction_delivery_confirmed': True})
    return {'delivery_id': delivery_id, 'completed': True, 'replayed': False, 'new_restrictions': matched}


@dataclass
class DeletionRecoveryCursor:
    """A worker's transient progress, scoped to one registered source account."""
    data_root: str
    source_account_id: str
    next_database: str = next(iter(SOURCE_DATABASES))
    positions: dict[str, tuple[str, str]] = field(default_factory=dict)


def deletion_recovery_cursor(paths, source_account):
    from backend.app.schemas.memory.values import canonical_uuid
    canonical_uuid(source_account)
    return DeletionRecoveryCursor(str(paths.root.resolve()), source_account)


def _pending_deletion_page(paths, source_account, database, *, after=None, limit=50):
    """Read only the next explicitly registered commands, never source history."""
    if database not in SOURCE_DATABASES or type(limit) is not int or not 1 <= limit <= 100:
        raise ValueError('Invalid deletion delivery scope')
    if after is not None and (not isinstance(after, tuple) or len(after) != 2 or any(not isinstance(value, str) or not value for value in after)):
        raise ValueError('Invalid deletion delivery position')
    path = registered_source_path(paths, source_account, database)
    if not path.is_file():
        return []
    if not safe_existing_file(path, paths.root):
        raise ValueError('Deletion source database is not a safe existing file')
    with connect_read_only(path) as db:
        position = ' AND (o.recorded_at,o.operation_id)>(?,?)' if after is not None else ''
        rows = db.execute('SELECT o.operation_id AS delivery_id,o.recorded_at FROM business_operations o JOIN business_operation_results r USING(operation_id) '
            "WHERE json_extract(o.original_command_json,'$.domain')=? AND json_extract(o.original_command_json,'$.action')='deliver' "
            'AND NOT EXISTS (SELECT 1 FROM business_operation_results done WHERE done.operation_id='
            "json_extract(o.original_command_json,'$.completion_operation_id'))" + position +
            ' ORDER BY o.recorded_at,o.operation_id LIMIT ?', (DOMAIN, *(after or ()), limit)).fetchall()
        return [dict(row) for row in rows]




def recover_registered_deletions(paths, source_account, *, limit=50, cursor=None):
    """Fairly retry registered deletions, independent of formation settings.

    Each failed/completed delivery and each failed directory read consumes one
    attempt. Empty reads retire that database until the next invocation, so
    directory reads are also bounded by limit + the fixed database count.
    """
    from backend.app.repositories.members.authorization_repository import MemberAuthorizationRepository
    if type(limit) is not int or not 1 <= limit <= 100:
        raise ValueError('Invalid deletion recovery limit')
    cursor = deletion_recovery_cursor(paths, source_account) if cursor is None else cursor
    if (not isinstance(cursor, DeletionRecoveryCursor)
            or (cursor.data_root, cursor.source_account_id) != (str(paths.root.resolve()), source_account)
            or cursor.next_database not in SOURCE_DATABASES or not isinstance(cursor.positions, dict)
            or any(database not in SOURCE_DATABASES for database in cursor.positions)):
        raise ValueError('Deletion recovery cursor belongs to a different scope')
    authorization = MemberAuthorizationRepository(paths)
    if not authorization.account_exists(source_account):
        raise SerenitaError('forbidden', 'MEMORY_DELETION_ACCOUNT_UNAVAILABLE', '来源账号不可用。')
    outcomes, database_failures, retired = [], [], set()
    databases, attempts, reads = tuple(SOURCE_DATABASES), 0, 0
    while attempts < limit and len(retired) < len(databases):
        database = cursor.next_database
        cursor.next_database = databases[(databases.index(database) + 1) % len(databases)]
        if database in retired:
            continue
        try:
            reads += 1
            rows = _pending_deletion_page(paths, source_account, database, after=cursor.positions.get(database), limit=1)
        except Exception as error:
            attempts += 1
            database_failures.append({'source_database': database, 'completed': False,
                'error_code': error.code if isinstance(error, SerenitaError) else type(error).__name__})
            retired.add(database)
            continue
        if not rows:
            # Revisit the incomplete prefix on the next wakeup, not repeatedly
            # within this invocation. New registrations can still advance tail.
            cursor.positions.pop(database, None)
            retired.add(database)
            continue
        row = rows[0]
        delivery_id = row['delivery_id']
        cursor.positions[database] = (row['recorded_at'], delivery_id)
        attempts += 1
        try:
            outcomes.append({**complete_deletion(paths, source_account, database, delivery_id), 'source_database': database})
        except Exception as error:
            outcomes.append({'delivery_id': delivery_id, 'source_database': database, 'completed': False,
                'error_code': error.code if isinstance(error, SerenitaError) else type(error).__name__})
    return {'deliveries': outcomes, 'database_failures': database_failures,
        'limit_reached': attempts >= limit, 'attempts_used': attempts, 'database_reads': reads, 'cursor': cursor}
