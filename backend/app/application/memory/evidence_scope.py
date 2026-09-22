"""Identity and execution limits required by evidence reads in any caller."""
from dataclasses import dataclass
from backend.app.core.cancellation import CancellationToken


@dataclass(frozen=True)
class MemoryEvidenceScope:
    account_id: str
    member_id: str
    task_id: str
    session_id: str | None = None
    cancellation_token: CancellationToken | None = None
    deadline: float | None = None
