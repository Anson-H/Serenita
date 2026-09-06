from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
import re
from typing import Any

import yaml

from backend.app.agent_runtime.skills.base import Skill, SkillDocument


_SKILL_NAME = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


class SkillReadError(RuntimeError):
    """Raised when a bundled Skill is malformed or cannot be read safely."""


@dataclass(frozen=True)
class SkillMetadata:
    """Small discovery payload read before a Skill is loaded."""

    name: str
    description: str
    directory: Path


@dataclass(frozen=True)
class SkillContract:
    """Host-only resource and Tool access metadata for one Skill directory."""

    allowed_tools: frozenset[str] = frozenset()
    required_references: tuple[str, ...] = ()


class DirectorySkill(Skill):
    """A Skill discovered from ``<name>/SKILL.md`` and loaded on demand."""

    def __init__(self, metadata: SkillMetadata):
        self.metadata = metadata
        self.name = metadata.name
        self.description = metadata.description

    def read(self, context) -> SkillDocument:
        contract = read_skill_contract(self.metadata.directory)
        return SkillDocument(
            name=self.name,
            content=read_skill_instructions(self.metadata.directory),
            allowed_tools=contract.allowed_tools,
        )


def discover_skills(root: str | Path) -> list[DirectorySkill]:
    """Discover immediate child directories containing a valid ``SKILL.md``."""

    skill_root = Path(root).resolve()
    if not skill_root.is_dir():
        raise SkillReadError(f"技能根目录不存在：{skill_root}")
    skills: list[DirectorySkill] = []
    for directory in sorted(skill_root.iterdir(), key=lambda item: item.name):
        if directory.is_dir() and (directory / "SKILL.md").is_file():
            skills.append(DirectorySkill(read_skill_metadata(directory)))
    return skills


@lru_cache(maxsize=None)
def read_skill_metadata(skill_directory: str | Path) -> SkillMetadata:
    """Read only frontmatter so discovery does not load full Skill instructions."""

    directory = Path(skill_directory).resolve()
    skill_file = directory / "SKILL.md"
    try:
        with skill_file.open("r", encoding="utf-8") as stream:
            if stream.readline().rstrip("\n") != "---":
                raise SkillReadError(f"{skill_file} 缺少 YAML frontmatter")
            frontmatter_lines: list[str] = []
            for line in stream:
                if line.rstrip("\n") == "---":
                    break
                frontmatter_lines.append(line)
            else:
                raise SkillReadError(f"{skill_file} 的 YAML frontmatter 未闭合")
    except (FileNotFoundError, OSError) as exc:
        raise SkillReadError(f"技能入口文件无法读取：{skill_file}") from exc

    metadata = _load_yaml_mapping("".join(frontmatter_lines), skill_file)
    name = str(metadata.get("name") or "").strip()
    description = str(metadata.get("description") or "").strip()
    if not _SKILL_NAME.fullmatch(name):
        raise SkillReadError(f"技能名称必须使用小写连字符格式：{name or '<empty>'}")
    if directory.name != name:
        raise SkillReadError(
            f"技能目录名必须与 frontmatter name 一致：{directory.name} != {name}"
        )
    if not description:
        raise SkillReadError(f"技能 {name} 缺少 description")
    return SkillMetadata(name=name, description=description, directory=directory)


@lru_cache(maxsize=None)
def read_skill_contract(skill_directory: str | Path) -> SkillContract:
    """Load optional product-specific runtime fields only on demand."""

    directory = Path(skill_directory).resolve()
    contract_file = directory / "runtime" / "serenita.yaml"
    if not contract_file.exists():
        return SkillContract()
    try:
        raw = contract_file.read_text(encoding="utf-8")
    except OSError as exc:
        raise SkillReadError(f"技能运行契约无法读取：{contract_file}") from exc
    value = _load_yaml_mapping(raw, contract_file)
    return SkillContract(
        allowed_tools=_string_set(
            value.get("allowed_tools"), field="allowed_tools", source=contract_file
        ),
        required_references=_string_tuple(
            value.get("required_references"),
            field="required_references",
            source=contract_file,
        ),
    )


@lru_cache(maxsize=None)
def read_skill_instructions(skill_directory: str | Path) -> str:
    """Load the complete instructions and required references for one Skill."""

    directory = Path(skill_directory).resolve()
    skill_file = directory / "SKILL.md"
    try:
        content = skill_file.read_text(encoding="utf-8")
    except (FileNotFoundError, OSError) as exc:
        raise SkillReadError(f"技能入口文件无法读取：{skill_file}") from exc
    match = re.match(r"\A---\r?\n.*?\r?\n---\r?\n(.*)\Z", content, re.DOTALL)
    body = match.group(1).strip() if match else ""
    if not body:
        raise SkillReadError(f"技能 {directory.name} 的说明正文不能为空")

    parts = [body]
    contract = read_skill_contract(directory)
    for relative_name in contract.required_references:
        reference = _resolve_skill_resource(directory, relative_name)
        try:
            reference_text = reference.read_text(encoding="utf-8").strip()
        except (FileNotFoundError, OSError) as exc:
            raise SkillReadError(f"技能参考文件无法读取：{reference}") from exc
        if not reference_text:
            raise SkillReadError(f"技能参考文件不能为空：{reference}")
        parts.append(reference_text)
    return "\n\n".join(parts)


def _resolve_skill_resource(directory: Path, relative_name: str) -> Path:
    candidate = (directory / relative_name).resolve()
    try:
        candidate.relative_to(directory)
    except ValueError as exc:
        raise SkillReadError(f"技能资源路径越界：{relative_name}") from exc
    if not candidate.is_file():
        raise SkillReadError(f"技能资源不存在：{candidate}")
    return candidate


def _load_yaml_mapping(raw: str, source: Path) -> dict[str, Any]:
    try:
        value = yaml.safe_load(raw)
    except yaml.YAMLError as exc:
        raise SkillReadError(f"YAML 格式无效：{source}") from exc
    if not isinstance(value, dict):
        raise SkillReadError(f"YAML 顶层必须是对象：{source}")
    return value




def _string_tuple(value: Any, *, field: str, source: Path) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise SkillReadError(f"{source} 的 {field} 必须是字符串数组")
    return tuple(item.strip() for item in value if item.strip())


def _string_set(value: Any, *, field: str, source: Path) -> frozenset[str]:
    return frozenset(_string_tuple(value, field=field, source=source))
