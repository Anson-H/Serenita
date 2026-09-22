"""Current task eligibility, reception state and processing detail snapshots."""
from contextlib import nullcontext
from backend.app.repositories.memory.transaction import memory_operation


class MemoryProcessingRepository:
    def __init__(self, repository):
        self.repository = repository

    def eligibility(self, actor, member, task):
        repo = self.repository
        with repo._transaction(actor, member) as (access, db):
            successor = db.execute('SELECT 1 FROM processing_attempts WHERE account_id=? AND member_id=? '
                'AND previous_attempt_id=? LIMIT 1', (access.account_id, member, task['attempt_id'])).fetchone()
            completed = task['task_kind'] == 'event_formation' and db.execute(
                "SELECT 1 FROM processing_attempts WHERE account_id=? AND member_id=? AND task_kind='event_formation' "
                "AND source_database IS ? AND change_id IS ? AND processing_status='completed' LIMIT 1",
                (access.account_id, member, task.get('source_database'), task.get('change_id'))).fetchone()
            return {'successor': bool(successor), 'completed_change': bool(completed),
                'record_cutoff': repo._cutoff(db, access)}

    def operation_applied(self, actor, member, operation_id):
        with self.repository._transaction(actor, member) as (access, db):
            return db is not None and db.execute('SELECT 1 FROM commits WHERE account_id=? AND member_id=? '
                'AND operation_id=?', (access.account_id, member, operation_id)).fetchone() is not None

    def delivery_snapshot(self, actor, member):
        """Read transport metadata without exposing inaccessible source contents."""
        with self.repository._transaction(actor, member) as (access, db):
            if db is None:
                return [], {}
            rows = db.execute(
                "SELECT p.*, c.sequence AS record_sequence FROM processing_attempts p "
                "JOIN commits c USING(commit_id) WHERE p.account_id=? AND p.member_id=? "
                "AND p.task_kind='intake_review' AND p.source_account_id IS NOT NULL ORDER BY c.sequence",
                (access.account_id, member)).fetchall()
            latest, maxima = {}, {}
            for raw in rows:
                row = self.repository._decode(dict(raw))
                key = (row['source_account_id'], row['source_database'], row['change_id'])
                latest[key] = row
                database = row['source_database']
                maxima[database] = max(maxima.get(database, 0), row['change_sequence'])
            return list(latest.values()), maxima


    def read_steps(self, actor, member, processing, *, step=None, snapshot=None):
        if not processing:
            return []
        repo = self.repository
        attempts = {row['attempt_id'] for row in processing['records'] if row['object_type'] == 'processing_attempt'}
        steps = []
        from backend.app.domain.memory.execution_references import retain_memory_references
        from backend.app.schemas.memory.values import MemoryReference
        with memory_operation('processing_steps'), (nullcontext(snapshot) if snapshot is not None else repo._transaction(actor, member)) as (access, db):
            for attempt in sorted(attempts):
                execution = repo._record(db, access, 'processing_attempt', attempt)
                if execution is None or not repo._visible(db, access, execution):
                    continue
                columns = 'p.*' if step else "p.attempt_id,p.progress_id,p.account_id,p.member_id,p.step_id,p.parent_step_id,p.status,p.error_code,NULL AS error_message,json_object('timing',json_extract(p.details_json,'$.timing'),'resumed',json_extract(p.details_json,'$.resumed'),'has_operations',json_type(p.details_json,'$.operations') IS NOT NULL) AS details_json"
                step_where = ' AND p.step_id=? AND p.parent_step_id IS ?' if step else ''
                for raw in db.execute('SELECT ' + columns + ', c.submitted_at, c.sequence AS record_sequence FROM processing_steps p '
                        'JOIN commits c USING(commit_id) WHERE p.attempt_id=? AND p.account_id=? AND p.member_id=?' + step_where + ' ORDER BY c.sequence',
                        (attempt, access.account_id, member, *(step or ()))):
                    steps.append(dict(raw))
        # Compressed step inputs can be large. Keep their decoding and reference
        # collection out of the shared database critical section.
        steps = [repo._decode(row) for row in steps]
        if step is None:
            # This projection only contains timing and boolean metadata. Its
            # attempts and sources were authorized in the snapshot above.
            fields = ('attempt_id', 'progress_id', 'step_id', 'parent_step_id', 'status', 'details',
                'error_code', 'error_message', 'submitted_at', 'record_sequence')
            return sorted(({key: row[key] for key in fields} for row in steps), key=lambda row: row['record_sequence'])
        references_by_step = []
        for row in steps:
            references = {}
            retain_memory_references(row['details'], references)
            references_by_step.append(references)
        checked = {}
        with memory_operation('step_access_recheck'), repo._transaction(actor, member) as (access, db):
            visible_attempts = {attempt: repo._visible(db, access, repo._record(db, access, 'processing_attempt', attempt)) for attempt in attempts}
            for row, references in zip(steps, references_by_step):
                visible = visible_attempts[row['attempt_id']]
                for key, value in references.items():
                    if key not in checked:
                        reference = MemoryReference.model_validate(value)
                        target = repo._record(db, access, reference.object_type, reference.object_id,
                            version=reference.version, item_id=reference.item_id, include_payload=False)
                        checked[key] = target is not None and repo._visible(db, access, target)
                    visible = visible and checked[key]
                if not visible:
                    row['details'] = {'unavailable_reason': '步骤引用的内容已删除或当前无权读取。'}
                    row['error_message'] = None
        steps = [{key: row[key] for key in ('attempt_id', 'progress_id', 'step_id', 'parent_step_id',
            'status', 'details', 'error_code', 'error_message', 'submitted_at', 'record_sequence')} for row in steps]
        return sorted(steps, key=lambda row: row['record_sequence'])


    def change_snapshot(self, actor, member, database, change_id):
        from backend.app.repositories.memory.processing.processing_catalog import read_processing_rows, group_processing
        from backend.app.repositories.memory.sources.evidence import read_change_title
        from backend.app.repositories.memory.processing.model_reader import MemoryModelReader
        repo = self.repository
        with repo._transaction(actor, member) as (live, db):
            cutoff = repo._cutoff(db, live)
            rows = read_processing_rows(repo, db, live, cutoff, change_keys={(database, change_id)}, compact=True)
            title = read_change_title(repo, live, {'source_database': database, 'change_id': change_id}, db)
            group = next((row for row in group_processing(rows, {(database, change_id): title})
                if row['group_id'] == f'change:{database}:{change_id}'), None)
            jobs = [row for row in rows if row['object_type'] == 'processing_attempt']
            inputs = MemoryModelReader(repo).read(actor, member, {row['attempt_id'] for row in jobs}, snapshot=(live, db))
            steps = self.read_steps(actor, member, group, snapshot=(live, db))
            eligible = live.can_edit
            states = db.execute('SELECT previous_attempt_id,task_kind,source_database,change_id,processing_status '
                'FROM processing_attempts WHERE account_id=? AND member_id=?', (live.account_id, member)).fetchall() if db is not None else []
        return group, jobs, inputs, steps, eligible, states

    def model_context(self, actor, member, database, change_id, source):
        from backend.app.repositories.memory.sources.source_access import MemorySourceAccess
        from backend.app.repositories.memory.sources.restrictions import source_restrictions_allow
        from backend.app.repositories.memory.processing.processing_catalog import processing_scope
        repo = self.repository
        source_access = MemorySourceAccess(repo.members, repo.paths)
        with repo.members.access_guard(actor, member) as access:
            grant_updated_at = access.grant_updated_at
        state = {'content_available': False, 'access_revision': '0:' + str(grant_updated_at)}
        original = []
        def check(access, db):
            allowed = source_access.check(access, source) and source_restrictions_allow(db, access, source['source_id'])
            revision = db.execute('SELECT COALESCE(max(c.sequence),0) FROM access_restrictions r JOIN commits c USING(commit_id) '
                'WHERE r.account_id=? AND r.member_id=?', (access.account_id, member)).fetchone()[0]
            revision = str(revision) + ':' + str(access.grant_updated_at)
            if not original:
                original.append(revision)
            state.update(content_available=allowed and revision == original[0], access_revision=revision)
            return state['content_available']
        def attempts(access, db):
            return processing_scope(db, access, repo._cutoff(db, access), {(database, change_id)})['processing_attempt']
        return attempts, check, state


