"""Medical reports plugin for Serenita."""

from backend.app.plugins.medical_report.registry import (
    PLUGIN_ID,
    SKILLS_ROOT,
    build_skills,
    build_tools,
)

__all__ = ("PLUGIN_ID", "SKILLS_ROOT", "build_skills", "build_tools")
