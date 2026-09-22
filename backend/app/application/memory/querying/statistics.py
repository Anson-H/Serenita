"""Read-only memory statistics with current business processing coverage."""

from backend.app.repositories.memory.reading.statistics import MemoryStatisticsRepository
from backend.app.schemas.memory.statistics import MemoryStatisticsRequest


class MemoryStatisticsService:
    def __init__(self, memory, formation=None):
        self.memory, self.formation = memory, formation
        self.repository = MemoryStatisticsRepository(memory.repository)
        from backend.app.application.memory.querying.experience import MemoryExperienceService
        self.experience = MemoryExperienceService(memory)
        from backend.app.repositories.memory.reading.coverage_repository import MemoryCoverageRepository
        self.coverage = MemoryCoverageRepository(memory.repository)


    def read(self, actor, member, values, *, binding=None):
        if self.formation is not None:
            self.formation.require_binding(actor, member, binding)
        request = self.memory._validate(MemoryStatisticsRequest, values)
        with self.memory.members.access_guard(actor, member):
            population = self.repository.read(actor, member, request, include_population=True)
            judgments = self.experience.judge(actor, member, population['_experience_events'], population['record_cutoff'])
            result = self.repository.read(actor, member, request, judgments=judgments, population=population)
            result["business_coverage"] = self.coverage.business_coverage(actor, member, result["record_cutoff"], request.source_categories)
            result["processing_coverage"] = self.coverage.processing_coverage(actor, member, result["record_cutoff"], request.source_categories)
            result["gaps"].extend(result["business_coverage"]["gaps"])
            if result["processing_coverage"]["pending_count"]:
                result["gaps"].append({"reason": "received_sources_not_fully_processed", "count": result["processing_coverage"]["pending_count"]})
            if not result["processing_coverage"]["complete"]:
                result["gaps"].append({"reason": "processing_coverage_budget"})
            if self.formation is not None:
                return self.formation.receipts(result, binding)
            return result


