from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass(frozen=True)
class MemoryItem:
    account: str
    namespace: str
    content: str
    created_at: Optional[datetime] = None


class MemoryStore:
    def save(self, item: MemoryItem) -> None:
        raise NotImplementedError

    def list(self, account: str, namespace: str):
        raise NotImplementedError
