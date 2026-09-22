"""Record actual reception operations without a model execution or task prerequisite."""
from contextlib import contextmanager
from copy import deepcopy
from backend.app.application.memory.progress import error_details
from backend.app.application.memory.step_timing import StepTiming
from backend.app.repositories.memory.sources.reception_journal import MemoryReceptionJournal


class MemoryReceptionRecorder(MemoryReceptionJournal):
    def __init__(self, paths, access, database, change_id):
        super().__init__(paths, access, database, change_id)
        self.paths = paths
        self.can_edit = access.can_edit

    @contextmanager
    def step(self, step_id, input, parent=None):
        timing = StepTiming()
        details = {'input': deepcopy(input), 'timing': timing.snapshot('running')}
        self.append(step_id, parent, 'running', details)
        try:
            yield details
        except Exception as error:
            failure = error_details(error)
            details.update(failure.pop('details', {}))
            details['timing'] = timing.snapshot('failed')
            self.append(step_id, parent, 'failed', details, **failure)
            if step_id == 'registered' and self.can_edit:
                from backend.app.repositories.business_memory_status_repository import BusinessMemoryStatusRepository
                BusinessMemoryStatusRepository(self.paths).fail_reception(self.account_id, self.member_id, self.database, self.change_id)
            raise
        else:
            details['timing'] = timing.snapshot('completed')
            self.append(step_id, parent, 'completed', details)
