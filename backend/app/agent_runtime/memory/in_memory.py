from typing import List

from backend.app.agent_runtime.memory.base import MemoryItem, MemoryStore


class InMemoryStore(MemoryStore):
    def __init__(self):
        self._items: List[MemoryItem] = []

    def save(self, item: MemoryItem) -> None:
        self._items.append(item)

    def list(self, account: str, namespace: str):
        return [
            item
            for item in self._items
            if item.account == account and item.namespace == namespace
        ]
