from typing import Any, Dict

from backend.app.agent_runtime.tools.base import Tool


class ToolNotFoundError(KeyError):
    pass


class ToolRegistry:
    def __init__(self):
        self._tools: Dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        if not str(tool.name or "").strip():
            raise ValueError("工具名称不能为空。")
        if getattr(tool, "model_exposure", "skill") not in {"direct", "skill"}:
            raise ValueError(
                f"工具 {tool.name} 的 model_exposure 必须是 direct 或 skill。"
            )
        if tool.name in self._tools:
            raise ValueError(f"重复的工具名称：{tool.name}")
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool:
        try:
            return self._tools[name]
        except KeyError:
            raise ToolNotFoundError(name)

    def has_tools(self) -> bool:
        return bool(self._tools)

    def catalog(self, *, context: Any = None) -> list[dict]:
        return [
            {
                "name": name,
                "description": str(getattr(tool, "description", "") or ""),
                "model_exposure": str(
                    getattr(tool, "model_exposure", "skill") or "skill"
                ),
                "input_schema": dict(tool.input_schema_for_context(context) or {}),
            }
            for name, tool in sorted(self._tools.items())
        ]
