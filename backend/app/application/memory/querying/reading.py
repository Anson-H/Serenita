"""Authorized memory reading and processing actions."""
class MemoryReadingService:
    """A read never creates a memory object or an agent task."""
    def __init__(self, memory):
        self.memory = memory

    def read(self, actor, member, values=None):
        values = values or {}
        query = values if values.get('business_changes') else {"object_types": ["event"], **values}
        result = self.memory.query(actor, member, query)
        # Settings are live access controls, including on a historical result.
        settings = self.memory.settings(actor, member)
        for row in result['objects']:
            if row['object_type'] != 'processing_attempt':
                continue
            current = values.get('view', 'current') != 'historical_saved' and settings['can_append']
            eligibility = self.memory.repository.processing.eligibility(actor, member, row)
            current = current and result['record_cutoff'] == eligibility['record_cutoff']
            from backend.app.application.memory.processing.processing_actions import project_processing_actions
            project_processing_actions(self.memory.repository, actor, member, row,
                live=current, successor=eligibility['successor'], completed_change=eligibility['completed_change'])
        from backend.app.domain.memory.read_results import readable_result
        return {**readable_result(result), "settings": settings, "view": values.get("view", "current"),
                "target_time": values.get("target_time"), "read_only": True}
