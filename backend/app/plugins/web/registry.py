from __future__ import annotations

from backend.app.agent_runtime.skills.base import Skill
from backend.app.agent_runtime.tools.base import Tool
from backend.app.plugins.runtime_context import PluginRuntimeContext
from backend.app.plugins.web.service import WebAccessService
from backend.app.plugins.web.tools import WebReadTool, WebSearchTool


PLUGIN_ID = "web"


def build_skills() -> list[Skill]:
    return []


def build_tools(*, runtime_context: PluginRuntimeContext) -> list[Tool]:
    configured_service = runtime_context.service(PLUGIN_ID, WebAccessService)
    service = configured_service.for_runtime(
        runtime_context.observation_resolver
    )
    return [WebSearchTool(service=service), WebReadTool(service=service)]
