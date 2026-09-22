"""Read-only memory statistics with current business processing coverage."""
from backend.app.core.time import local_now
import json

from backend.app.domain.memory.sources import BUSINESS_SOURCE_DATABASES
from backend.app.repositories.memory.sources.source_access import SOURCE_REGISTRATIONS
from backend.app.core.errors import SerenitaError

MAX_COVERAGE_CHANGES = 20000


class MemoryCoverageRepository:
    def __init__(self, repository):
        from backend.app.repositories.memory.sources.business_sources import MemoryBusinessSourceRepository
        self.repository = repository
        self.business = MemoryBusinessSourceRepository(repository)

    def business_coverage(self, actor, member, cutoff, categories):
        repo, business = self.repository, self.business
        result, gaps = [], []
        with repo._transaction(actor, member) as (access, db):
            setting = repo._settings(db, access)
            enabled = set(setting.get("source_categories", []))
            selected = set(categories) if categories else enabled
            enabled_at = setting.get('effective_at')
            for database in BUSINESS_SOURCE_DATABASES:
                relevant = set().union(*(registration.categories for registration in SOURCE_REGISTRATIONS.values() if registration.database == database)) & selected
                if not relevant:
                    continue
                active_categories = relevant & enabled if setting['formation_state'] == 'enabled' else set()
                scope = {"source_database": database, "source_categories": sorted(relevant), "scope": "post_enable_member_business_changes",
                         "enabled_at": enabled_at, "observed_change_sequence": 0, "pending_count": 0, "pending": [], "complete": True}
                if not active_categories:
                    scope.update(complete=False, reason="source_range_not_enabled")
                    result.append(scope)
                    gaps.append({"source_database": database, "reason": "source_range_not_enabled"})
                    continue
                if relevant - active_categories:
                    scope["complete"] = False
                    gaps.append({"source_database": database, "reason": "source_categories_not_enabled", "source_categories": sorted(relevant - active_categories)})
                try:
                    with business.sources._database(access.account_id, database) as connection:
                        scope["observed_change_sequence"] = connection.execute("SELECT COALESCE(max(change_sequence),0) FROM business_changes WHERE member_id=?", (member,)).fetchone()[0]
                        changes = connection.execute("SELECT change_id,change_sequence,member_id,scope_kind,resource_type,resource_id,context_json "
                            "FROM business_changes WHERE member_id=? AND (? IS NULL OR recorded_at>=?) ORDER BY change_sequence LIMIT ?",
                            (member, enabled_at, enabled_at, MAX_COVERAGE_CHANGES + 1)).fetchall()
                except FileNotFoundError:
                    changes = []
                    scope["complete"] = False
                    gaps.append({"source_database": database, "reason": "business_database_unavailable"})
                if len(changes) > MAX_COVERAGE_CHANGES:
                    scope["complete"] = False
                    gaps.append({"source_database": database, "reason": "business_coverage_budget"})
                for raw in changes[:MAX_COVERAGE_CHANGES]:
                    registration = SOURCE_REGISTRATIONS.get(raw["resource_type"])
                    if registration is None or registration.database != database:
                        scope["complete"] = False
                        gaps.append({"source_database": database, "reason": "unregistered_business_change"})
                        continue
                    category = next(iter(registration.categories))
                    if category not in active_categories:
                        continue
                    change = dict(raw)
                    change["context"] = json.loads(change.pop("context_json"))
                    try:
                        source = business.identity(access, database, change)
                    except SerenitaError:
                        scope["complete"] = False
                        gaps.append({"source_database": database, "reason": "business_source_identity_unavailable"})
                        continue
                    if not business.sources.check(access, {**source, "account_id": access.account_id, "member_id": member}):
                        continue
                    attempt = self._formation_attempt(repo, db, access, database, raw["change_id"], cutoff)
                    state = attempt.get("processing_status") if attempt else None
                    if state != "completed":
                        scope["pending_count"] += 1
                        if len(scope["pending"]) < 100:
                            scope["pending"].append({"change_id": raw["change_id"], "change_sequence": raw["change_sequence"],
                                "status": state or "not_received"})
                if scope["pending_count"]:
                    gaps.append({"source_database": database, "reason": "business_changes_not_formed", "count": scope["pending_count"]})
                scope["pending_details_complete"] = scope["pending_count"] <= len(scope["pending"])
                result.append(scope)
        return {"checked_at": local_now().isoformat(), "memory_record_cutoff": cutoff, "sources": result,
                "complete": all(item["complete"] for item in result), "gaps": gaps,
                "limits": {"changes_per_database": MAX_COVERAGE_CHANGES, "pending_details_per_database": 100},
                "account_references": "explicitly_selected_only", "pre_enable_history": "not_asserted_complete"}

    @staticmethod
    def _formation_attempt(repo, db, access, database, change_id, cutoff):
        if db is None:
            return None
        raw = db.execute("SELECT p.attempt_id FROM processing_attempts p JOIN commits c USING(commit_id) "
            "WHERE p.account_id=? AND p.member_id=? AND p.source_database=? AND p.change_id=? "
            "AND p.task_kind='event_formation' AND c.sequence<=? ORDER BY c.sequence DESC LIMIT 1",
            (access.account_id, access.member_id, database, change_id, cutoff)).fetchone()
        row = repo._record(db, access, "processing_attempt", raw[0], cutoff=cutoff) if raw else None
        return repo._project(db, access, row, cutoff) if row and repo._visible(db, access, row) else None

    def processing_coverage(self, actor, member, cutoff, categories):
        from backend.app.repositories.memory.sources.evidence import read_change
        repo = self.repository
        pending, count = [], 0
        with repo._transaction(actor, member) as (access, db):
            rows = [] if db is None else db.execute(
                "SELECT DISTINCT p.source_database,p.change_id FROM processing_attempts p JOIN commits c USING(commit_id) "
                "WHERE p.account_id=? AND p.member_id=? AND p.task_kind='event_formation' AND p.change_id IS NOT NULL AND c.sequence<=? "
                "ORDER BY p.source_database,p.change_id LIMIT ?",
                (access.account_id, member, cutoff, MAX_COVERAGE_CHANGES + 1)).fetchall()
            for row in rows[:MAX_COVERAGE_CHANGES]:
                attempt = self._formation_attempt(repo, db, access, row['source_database'], row['change_id'], cutoff)
                if attempt is None:
                    continue
                change = read_change(repo, access, dict(row), db)
                if categories and change['source_category'] not in categories:
                    continue
                state = attempt.get('processing_status')
                if state != 'completed':
                    count += 1
                    if len(pending) < 100:
                        pending.append({**dict(row), 'source_category': change['source_category'],
                            'attempt_id': attempt['attempt_id'], 'status': state or 'processing_result_unavailable'})
        return {'scope': 'visible_business_changes_with_formation_attempts', 'pending_count': count,
            'pending': pending, 'pending_details_complete': count <= 100, 'complete': len(rows) <= MAX_COVERAGE_CHANGES,
            'event_time_filter': 'cannot_classify_unprocessed_contents', 'memory_record_cutoff': cutoff}

