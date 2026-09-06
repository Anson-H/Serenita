"""Generic Skill discovery and reading for Serenita's main runtime."""

from pathlib import Path

from backend.app.agent_runtime.skills.base import SkillDocument
from backend.app.agent_runtime.skills.loader import (
    DirectorySkill,
    SkillContract,
    SkillReadError,
    SkillMetadata,
    discover_skills,
    read_skill_contract,
    read_skill_instructions,
    read_skill_metadata,
)


def build_builtin_skills(root: str | Path | None = None) -> list[DirectorySkill]:
    """Discover Skills from plugins, or from an explicit root in tests/tools."""

    if root is not None:
        return discover_skills(root)
    from backend.app.plugins.registry import build_builtin_skills as build_plugin_skills

    return list(build_plugin_skills())


__all__ = [
    "DirectorySkill",
    "SkillDocument",
    "SkillContract",
    "SkillReadError",
    "SkillMetadata",
    "build_builtin_skills",
    "discover_skills",
    "read_skill_contract",
    "read_skill_instructions",
    "read_skill_metadata",
]
