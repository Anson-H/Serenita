from dataclasses import dataclass, field
from typing import Any, Dict


@dataclass(frozen=True)
class ToolResult:
    name: str
    output: Dict[str, Any] = field(default_factory=dict)


class Tool:
    name = "tool"
    description = ""

    def run(self, arguments: Dict[str, Any]) -> ToolResult:
        raise NotImplementedError
