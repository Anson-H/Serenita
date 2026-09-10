"""Medication tools executed through the medication service."""

from copy import deepcopy

from backend.app.agent_runtime.tools.base import Tool, ToolResult
from backend.app.agent_runtime.tools.pagination import automatic_pages
from backend.app.application.medication_service import MedicationService
from backend.app.domain.medications import medication_name
from backend.app.plugins.medication.constants import NAMES, PLUGIN_ID
from backend.app.schemas.medication import IDS
from backend.app.plugins.resource_effects import resource_effects


class MedicationTool(Tool):
    def __init__(self, context, name, description, schema, operation, kind=None):
        self.context = context
        self.name = name
        self.description = description
        self.input_schema = schema
        self.operation = operation
        self.kind = kind
        self.service = context.service(PLUGIN_ID, MedicationService)

    def input_schema_for_context(self, context):
        schema = deepcopy(self.input_schema)
        if "sources" in schema["properties"]:
            schema["properties"]["sources"]["items"]["properties"]["resource_id"]["enum"] = sorted(
                str(value) for value in (context.memory.get("visible_attachments") or {})
            )
        return schema

    def bind_runtime_arguments(self, arguments, *, context, observations):
        if (
            context.account_id != self.context.account_id
            or context.member_id != self.context.member_id
        ):
            raise PermissionError("用药工具与当前任务成员不一致。")
        bound = dict(arguments)
        if "sources" in self.input_schema["properties"]:
            visible = context.memory.get("visible_attachments") or {}
            if any(source["resource_id"] not in visible for source in bound.get("sources", [])):
                raise PermissionError("药品原件必须来自当前会话可见附件。")
        return bound

    def read_uploads(self, references):
        uploads = []
        for reference in references:
            source = self.context.read_conversation_attachment(reference["resource_id"])
            uploads.append({
                "original_filename": source.original_filename,
                "mime_type": source.mime_type,
                "content": source.content_bytes,
                "purpose": reference["purpose"],
            })
        return uploads

    def run(self, arguments):
        arguments = deepcopy(arguments)
        if self.operation in ("catalog", "information"):
            return automatic_pages(lambda cursor: self._run({**arguments, "cursor": cursor, "limit": 24}))
        return self._run(arguments)

    def _run(self, arguments):
        v = dict(arguments)
        actor, member = self.context.account_id, self.context.member_id
        op, kind = self.operation, self.kind
        effects = {}
        affected = None
        if op == "delete":
            affected = self.service.read(actor, member, kind, v[IDS[kind]])
        batch_identity = None
        if kind == "batch":
            batch = affected or (self.service.read(actor, member, kind, v[IDS[kind]]) if op != "create" else v)
            batch_identity = self.service.read(actor, member, "medication", batch["medication_id"])
        if op == "catalog":
            output = self.service.catalog(actor, member, kind, **v)
        elif op == "information":
            output = self.service.read_information(actor, member, **v)
            refs = [{
                'resource_type': 'medication_source', 'resource_id': source['resource_id'],
                'medication_id': item['medication_id'], 'member_id': member,
            } for item in output['items'] for source in item.get('sources', [])]
            if refs:
                effects['model_resource_refs'] = refs
        elif op == "inventory":
            output = self.service.read_inventory(actor, member, v['medication_id'])
        elif op == "read":
            output = self.service.read(actor, member, kind, v[IDS[kind]])
        elif op == "sources":
            uploads = self.read_uploads(v["sources"])
            output = self.service.add_sources(actor, member, v["medication_id"], uploads, v["request_id"])
        elif op == "create":
            request_id = v.pop("request_id")
            parent = v.pop("medication_id", None) if kind == "batch" else None
            uploads = self.read_uploads(v.pop("sources", [])) if kind == "medication" else None
            output = self.service.save(
                actor, member, kind, v, request_id=request_id, medication_id=parent, uploads=uploads
            )
        elif op == "update":
            object_id = v.pop(IDS[kind])
            output = self.service.save(actor, member, kind, v, object_id=object_id)
        elif op == "delete":
            output = self.service.delete(actor, member, kind, v[IDS[kind]])
        else:
            raise ValueError("未知的用药操作")
        if kind in ("medication", "plan", "batch"):
            items = output['items'] if op in ('information', 'catalog') else [affected if op == "delete" else output]
            effects["affected_resource_refs" if op == "delete" else "resource_refs"] = []
            for item in items:
                if kind == "medication":
                    item['path'] = f"/health/{member}/medications/catalog/{item[IDS[kind]]}"
                reference = {
                    "resource_type": NAMES[kind],
                    "resource_id": item[IDS[kind]],
                    "member_id": member,
                    "name": medication_name(item if kind == "medication" else batch_identity if kind == "batch" else item["medication_identity"]),
                    "created_at": item["created_at"],
                    "updated_at": item["updated_at"],
                }
                if kind == "batch":
                    reference["medication_id"] = item["medication_id"]
                change = {"create": "created", "update": "modified", "delete": "deleted", "sources": "source_linked"}.get(op)
                for key, values in resource_effects(reference, change).items():
                    effects.setdefault(key, []).extend(values)
        return ToolResult(name=self.name, output=output, effects=effects)
