from copy import deepcopy

from backend.app.agent_runtime.tools.base import Tool, ToolResult
from backend.app.agent_runtime.tools.pagination import automatic_pages, paginated_collection
from backend.app.application.medical_log_service import MedicalLogService
from backend.app.plugins.medical_log.resources import log_reference
from backend.app.plugins.resource_effects import resource_effects


class MedicalLogTool(Tool):
    def __init__(self, context):
        self.account_id, self.member_id = context.account_id, context.member_id
        self.service = context.service("medical_log", MedicalLogService)

    def bind_runtime_arguments(self, arguments, *, context, observations):
        if context.account_id != self.account_id or context.member_id != self.member_id:
            raise PermissionError("健康日记工具与当前任务的成员不一致。")
        return dict(arguments)

    def run(self, arguments):
        values = deepcopy(arguments)
        actor, member = self.account_id, self.member_id
        effects = {}
        if self.name == "read_log":
            return automatic_pages(lambda cursor: paginated_collection(
                name=self.name,
                output=self.service.read(actor, member, **values, cursor=cursor, limit=24)
                if cursor is not None else self.service.read(actor, member, **values, limit=24),
                collection_field="medical_logs", page_size=24,
            ))
        elif self.name == "create_log":
            output = self.service.create(actor, member, values)
        elif self.name == "update_log":
            output = self.service.update(actor, member, values.pop("medical_log_id"), values)
        else:
            affected = self.service.read(actor, member, medical_log_ids=[values["medical_log_id"]])["medical_logs"][0]
            output = self.service.delete(actor, member, values["medical_log_id"])
            effects = resource_effects(log_reference(affected), "deleted")
        if "medical_log" in output:
            effects = resource_effects(log_reference(output["medical_log"]),
                                       "created" if self.name == "create_log" else "modified")
        return ToolResult(name=self.name, output=output, effects=effects)
