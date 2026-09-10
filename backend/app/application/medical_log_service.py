from contextlib import contextmanager
from pydantic import ValidationError
from backend.app.core.errors import raise_error
from backend.app.repositories.member_repository import MemberRepository
from backend.app.repositories.medical_log_repository import MedicalLogRepository
from backend.app.schemas.medical_log import MedicalLogCreate, MedicalLogUpdate, MedicalLogQuery, MedicalLogReadQuery


class MedicalLogService:
    def __init__(self, members=None):
        self.members = members or MemberRepository()

    @contextmanager
    def repository(self, actor_account_id, member_id, *, write=False):
        with self.members.access_guard(actor_account_id, member_id, write=write) as access:
            repository = MedicalLogRepository(access.account_id, self.members.paths)
            try:
                yield repository
            except LookupError as exc:
                raise_error("missing", "MEDICAL_LOG_NOT_FOUND", str(exc))
            except ValueError as exc:
                raise_error("invalid_input", "MEDICAL_LOG_ARGUMENTS_INVALID", str(exc))

    def _validate(self, schema, values):
        try:
            return schema.model_validate(values)
        except ValidationError as exc:
            raise_error("invalid_input", "MEDICAL_LOG_ARGUMENTS_INVALID", str(exc))

    def catalog(self, actor, member_id, **filters):
        values = self._validate(MedicalLogQuery, filters).model_dump()
        with self.repository(actor, member_id) as repository:
            return {"member_id": member_id, **repository.catalog(member_id, values)}

    def read(self, actor, member_id, **filters):
        values = self._validate(MedicalLogReadQuery, filters).model_dump()
        with self.repository(actor, member_id) as repository:
            return {"member_id": member_id, **repository.read(member_id, values)}

    def create(self, actor, member_id, values):
        payload = self._validate(MedicalLogCreate, values).model_dump(exclude_unset=True)
        with self.repository(actor, member_id, write=True) as repository:
            return {"member_id": member_id, "medical_log": repository.create(member_id, payload)}

    def update(self, actor, member_id, medical_log_id, values):
        payload = self._validate(MedicalLogUpdate, values).model_dump(exclude_unset=True)
        with self.repository(actor, member_id, write=True) as repository:
            return {"member_id": member_id, "medical_log": repository.update(member_id, medical_log_id, payload)}

    def delete(self, actor, member_id, medical_log_id):
        with self.repository(actor, member_id, write=True) as repository:
            return repository.delete(member_id, medical_log_id)
