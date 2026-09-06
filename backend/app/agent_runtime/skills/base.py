from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SkillDocument:
    """Skill instructions read from disk plus host-only execution metadata."""

    name: str
    content: str
    allowed_tools: frozenset[str] = frozenset()


class Skill:
    name = "skill"

    def read(self, context) -> SkillDocument:
        raise NotImplementedError
