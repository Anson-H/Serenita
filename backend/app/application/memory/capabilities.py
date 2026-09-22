"""Public read-capability assembly; internal services keep their own responsibilities."""
from backend.app.application.memory.querying.query import MemoryQueryService
from backend.app.application.memory.querying.reading import MemoryReadingService
from backend.app.application.memory.querying.graph import MemoryGraphService
from backend.app.application.memory.processing.changes import MemoryChangesService
from backend.app.application.memory.processing.processing_catalog import MemoryProcessingCatalog
from backend.app.application.memory.querying.statistics import MemoryStatisticsService


class MemoryReadServices:
    def __init__(self, memory):
        self.search = MemoryQueryService(memory)
        self.reading = MemoryReadingService(memory)
        self.graph = MemoryGraphService(memory)
        self.changes = MemoryChangesService(memory)
        self.processing = MemoryProcessingCatalog(memory)
        self.statistics = MemoryStatisticsService(memory)


class MemoryConversationReads:
    """Assemble the four conversation reads with one evidence issuer and request scope."""
    def __init__(self,memory,*,cancellation_token=None,deadline=None):
        from backend.app.application.memory.evidence_service import MemoryEvidenceService
        self.evidence=MemoryEvidenceService(memory)
        self.search=MemoryQueryService(memory,cancellation_token=cancellation_token,deadline=deadline)
        self.graph=MemoryGraphService(memory,self.evidence)
        self.statistics=MemoryStatisticsService(memory,self.evidence)
