"""Authorized memory capabilities shared by HTTP and agent tools."""
from backend.app.core.time import local_now


from pydantic import ValidationError

from backend.app.core.errors import SerenitaError
from backend.app.repositories.members.repository import MemberRepository
from backend.app.schemas.memory.append import (
    MemoryWrite, MemoryQuery, MemorySettingInput, stable_memory_id,
)
from backend.app.schemas.memory.requests import MemoryReadRequest, MemorySettingsSave


class MemoryService:
    def __init__(self, members=None, *, repository=None, models=None):
        self.members = members or MemberRepository()
        self.paths = self.members.paths
        if repository is None:
            from backend.app.repositories.memory.repository import MemoryRepository
            from backend.app.repositories.memory.sources.source_access import MemorySourceAccess

            repository = MemoryRepository(paths=self.paths, member_repository=self.members,
                                          source_access_check=MemorySourceAccess(self.members, self.paths).check)
        self.repository = repository
        if models is None:
            from backend.app.application.models.provider_service import ModelProviderService

            models = ModelProviderService(paths=self.paths)
        self.models = models
        from backend.app.application.memory.sources.business_sources import MemoryBusinessSources
        self.business_sources = MemoryBusinessSources(self)

    @staticmethod
    def _validate(schema, values):
        try:
            return schema.model_validate(values)
        except ValidationError as exc:
            raise SerenitaError(
                "invalid_input", "MEMORY_ARGUMENTS_INVALID", "记忆参数不符合当前契约。",
                details={"validation_errors": exc.errors(include_input=False, include_context=False)},
            ) from exc

    def settings(self, actor_account_id, member_id):
        with self.members.access_guard(actor_account_id, member_id) as access:
            current = self.repository.settings(actor_account_id, member_id)
            return {
                "member_id": member_id,
                "setting": current if current["setting_id"] is not None else None,
                "formation_state": current["formation_state"],
                "source_categories": current["source_categories"],
                "can_manage": access.permission == "owner",
                "can_append": access.can_edit,
            }

    def save_settings(self, actor_account_id, member_id, values):
        command = self._validate(MemorySettingsSave, values)
        with self.members.access_guard(actor_account_id, member_id, write=True) as access:
            if access.permission != "owner":
                raise SerenitaError("forbidden", "MEMORY_OWNER_REQUIRED", "只有健康档案所有者可以管理记忆形成设置。")
            model = self.models.default_model_for_account(access.account_id, "text_embedding")
            previous = self.repository.settings(actor_account_id, member_id)
            effective_at = local_now().isoformat()
            if (previous.get('setting_id') and previous['formation_state'] == command.formation_state
                    and set(previous['source_categories']) == set(command.source_categories)):
                effective_at = previous['effective_at']
            setting = self._validate(MemorySettingInput, {
                "setting_id": stable_memory_id(member_id, command.operation_id, "memory_setting", "settings"),
                "previous_setting_id": command.previous_setting_id,
                "embedding_model_id": model["model_id"] if model else None,
                "source_categories": command.source_categories,
                "reason": command.reason,
                "formation_state": command.formation_state,
                "effective_at": effective_at,
            })
            result = self.repository.write(
                actor_account_id, member_id, command.operation_id,
                MemoryWrite(settings=[setting]),
                command=command.model_dump(mode="json"),
            )
            return {**self.settings(actor_account_id, member_id), "commit": result}

    def query(self, actor_account_id, member_id, values=None):
        query = self._validate(MemoryReadRequest, values or {})
        if query.business_changes:
            return self.repository.evidence.read_change_observation(actor_account_id, member_id,
                [ref.model_dump() for ref in query.business_changes])
        references = query.references
        filters = MemoryQuery.model_validate(query.model_dump(exclude={"references", "business_changes"}))
        if references:
            return self.repository.read(actor_account_id, member_id, references, query=filters)
        return self.repository.query(actor_account_id, member_id, filters)
