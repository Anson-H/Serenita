"""Host-supplied dependency boundary for the pinned SAG algorithms.

No global model clients, separate SQL database or alternate search strategy.
The application must pass a runtime implementing the operations used by each stage.
"""
from typing import Protocol


class SAGRuntime(Protocol):
    pass
