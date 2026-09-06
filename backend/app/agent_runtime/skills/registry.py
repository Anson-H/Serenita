from typing import Dict

from backend.app.agent_runtime.skills.base import Skill


class SkillRegistry:
    def __init__(self):
        self._skills: Dict[str, Skill] = {}

    def register(self, skill: Skill) -> None:
        if not str(skill.name or "").strip():
            raise ValueError("技能名称不能为空。")
        if skill.name in self._skills:
            raise ValueError(f"重复的技能名称：{skill.name}")
        self._skills[skill.name] = skill

    def get(self, name: str) -> Skill:
        try:
            return self._skills[name]
        except KeyError as exc:
            raise SkillNotFoundError(name) from exc

    def catalog(self) -> list[dict[str, str]]:
        return [
            {
                "name": name,
                "description": str(getattr(skill, "description", "") or ""),
            }
            for name, skill in sorted(self._skills.items())
        ]


class SkillNotFoundError(KeyError):
    pass
