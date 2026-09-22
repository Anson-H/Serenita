"""Discover body metric skills and assemble their tools."""

from pathlib import Path

from backend.app.agent_runtime.skills.loader import discover_skills

from backend.app.plugins.body_metric.tools import create_tools
from backend.app.plugins.body_metric.resources import resolve_resource_state as resolve_resource_state

PLUGIN_ID = "body_metric"


def build_skills():
    return discover_skills(Path(__file__).parent / "skills")


def build_tools(*, runtime_context):
    return create_tools(runtime_context=runtime_context)
