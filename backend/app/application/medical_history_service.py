from pydantic import ValidationError

from backend.app.core.member_errors import member_error
from backend.app.repositories.medical_history_repository import MedicalHistoryRepository
from backend.app.repositories.member_repository import MemberRepository
from backend.app.schemas.medical_history import MedicalHistoryUpdate, selected_history_fields


class MedicalHistoryService:
    def __init__(self, members: MemberRepository | None = None):
        self.members = members or MemberRepository()
        self.repository = MedicalHistoryRepository(self.members.paths)

    def read(self, actor_account_id, member_id, fields=None):
        try:
            selected = selected_history_fields(fields)
        except ValueError as exc:
            member_error("MEDICAL_HISTORY_ARGUMENTS_INVALID", str(exc), "invalid_input")
        with self.members.access_guard(actor_account_id, member_id) as access:
            return self.repository.read(access, selected)

    def update(self, actor_account_id, member_id, values):
        try:
            payload = MedicalHistoryUpdate.model_validate(values)
        except ValidationError as exc:
            member_error("MEDICAL_HISTORY_ARGUMENTS_INVALID", str(exc), "invalid_input")
        normalized = {name: (value.strip() or None) if value is not None else None
                      for name, value in payload.model_dump(exclude_unset=True).items()}
        with self.members.access_guard(actor_account_id, member_id, write=True) as access:
            return self.repository.update(access, normalized)
