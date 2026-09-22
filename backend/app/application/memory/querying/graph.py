"""Project existing memory objects and fixed Event relations without persisting edges."""

from backend.app.schemas.memory.graph import MemoryGraphRead
from backend.app.repositories.memory.reading.graph_repository import MemoryGraphRepository


class MemoryGraphService:
    def __init__(self, memory, formation=None):
        self.memory, self.formation = memory, formation
        self.repository = MemoryGraphRepository(memory.repository)

    def read(self, actor, member, values, *, binding=None):
        request = self.memory._validate(MemoryGraphRead, values)
        if binding is not None:
            self.formation.require_binding(actor, member, binding)
        result = self.repository.read(actor, member, request)
        result['member_id'] = member
        result['read_query'] = request.model_dump(mode='json')
        result['coverage']['complete'] = result['complete']
        if binding is not None:
            result = self.formation.receipts(result, binding)
        return result


