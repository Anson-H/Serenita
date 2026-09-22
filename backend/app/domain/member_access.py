"""Member authorization values and their explicit live permission guard."""
from __future__ import annotations
from contextlib import AbstractContextManager
from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol


class MemberAccessGuard(Protocol):
    def access_guard(self, actor_account_id: str, member_id: str, *, write: bool = False) -> AbstractContextManager[MemberAccess]: ...


@dataclass(frozen=True)
class MemberAccess:
    actor_account_id: str
    account_id: str
    actor_account: str
    owner_account: str
    member_id: str
    permission: str
    grant_updated_at: datetime | None
    is_default: bool
    access_repository: MemberAccessGuard = field(repr=False, compare=False)

    @property
    def can_edit(self) -> bool:
        return self.permission in {"owner", "edit"}

    def guard(self, *, write: bool = False):
        return self.access_repository.access_guard(
            self.actor_account_id, self.member_id, write=write
        )

    def check(self, *, write: bool = False) -> MemberAccess:
        with self.guard(write=write) as live:
            return live
