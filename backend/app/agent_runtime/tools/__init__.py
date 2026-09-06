"""Generic Tool abstractions for Serenita's main runtime."""

from backend.app.agent_runtime.tools.base import Tool, ToolResult
from backend.app.agent_runtime.tools.registry import ToolNotFoundError, ToolRegistry

__all__ = ("Tool", "ToolNotFoundError", "ToolRegistry", "ToolResult")
