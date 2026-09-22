"""Authorized source reads and immutable evidence scopes for application services."""
from backend.app.core.errors import SerenitaError
from backend.app.schemas.memory.evidence import source_key
from backend.app.repositories.memory.sources.evidence import change_references, read_change, change_source, check_change
from backend.app.repositories.memory.facts.event_evidence import event_references


class MemoryEvidenceRepository:
    def __init__(self, repository):
        self.repository = repository

    def read_changes(self, actor, member, references, *, sources=False):
        with self.repository._transaction(actor, member) as (access, db):
            rows = [read_change(self.repository, access, ref, db) for ref in references]
            return [change_source(row) for row in rows] if sources else rows

    def check_changes(self, actor, member, references):
        with self.repository._transaction(actor, member) as (access, db):
            for ref in references:
                check_change(self.repository, access, ref, db)

    def source_references(self, actor, member, objects):
        with self.repository._transaction(actor, member) as (access, db):
            refs = {source_key(ref): ref for row in objects
                for ref in change_references(self.repository, db, access, row)}
            return list(refs.values())

    def event_sources(self, actor, member, events, cutoff):
        """Return exact authorized events and their source texts at the caller's cutoff."""
        result = []
        repo = self.repository
        with repo._transaction(actor, member) as (access, db):
            cutoff = repo._cutoff(db, access, cutoff)
            for supplied in events:
                row = repo._require(db, access, 'event', supplied['event_id'], cutoff=cutoff)
                sources = [{'reference': reference,
                    'text': change_source(read_change(repo, access, reference, db))['content_text']}
                    for reference in event_references(db, access, row['event_id'])]
                result.append({key: row[key] for key in ('event_id', 'title', 'summary', 'content')} | {'sources': sources})
        return result

    def check_visible_objects(self, actor, member, objects, *, code='MEMORY_OBJECT_UNAVAILABLE'):
        with self.repository._transaction(actor, member) as (access, db):
            if any(not self.repository._visible(db, access, row) for row in objects):
                raise SerenitaError('forbidden', code, '采用的记忆依据当前不可读取。')

    def source_access(self, actor, member, source):
        from backend.app.repositories.memory.sources.restrictions import source_restrictions_allow
        with self.repository._transaction(actor, member) as (access, db):
            allowed = source_restrictions_allow(db, access, source['source_id'])
            sequence = db.execute('SELECT COALESCE(max(c.sequence),0) FROM access_restrictions r '
                'JOIN commits c USING(commit_id) WHERE r.account_id=? AND r.member_id=?',
                (access.account_id, member)).fetchone()[0] if db is not None else 0
            return allowed, str(sequence) + ':' + str(access.grant_updated_at)

    def read_change_observation(self, actor, member, references):
        with self.repository._transaction(actor, member) as (access, db):
            changes = [read_change(self.repository, access, ref, db) for ref in references]
            cutoff = self.repository._cutoff(db, access)
            return {'member_id': member, 'objects': [], 'business_changes': changes, 'record_cutoff': cutoff,
                'coverage': {'returned_changes': len(changes), 'complete': True},
                'gaps': [], 'unread': [], 'next_cursor': None}

    def require_coverage(self, actor, member, observed, cutoff):
        from backend.app.domain.memory.sources import SOURCE_REGISTRATIONS
        repo = self.repository
        with repo._transaction(actor, member) as (access, db):
            has_sources = False
            for ref in observed['references']:
                row = repo._require(db, access, ref['object_type'], ref['object_id'],
                    version=ref.get('version'), item_id=ref.get('item_id'), cutoff=cutoff)
                has_sources |= bool(change_references(repo, db, access, row))
            query = observed.get('query') or {}
            categories = query.get('source_categories') or (repo._settings(db, access)['source_categories']
                if not query.get('references') else [])
            if not has_sources and not any(category in registration.categories
                    for category in categories for registration in SOURCE_REGISTRATIONS.values()):
                raise SerenitaError('invalid_input', 'MEMORY_COVERAGE_SCOPE_MISSING', '读取结果没有可核对的实际来源范围。')
