"""Register the medication plugin's skills, tools, and resource resolvers."""

from pathlib import Path

from backend.app.agent_runtime.skills.loader import discover_skills
from backend.app.plugins.medication.constants import PLUGIN_ID as PLUGIN_ID
from backend.app.plugins.medication.resources import (
    resolve_model_resource as resolve_model_resource,
    resolve_resource_state as resolve_resource_state,
)
from backend.app.plugins.medication.tools import create_tools

SKILLS_ROOT = Path(__file__).resolve().parent / "skills"


def build_skills():
    return discover_skills(SKILLS_ROOT)


def build_tools(*, runtime_context):
    return create_tools(runtime_context=runtime_context)
