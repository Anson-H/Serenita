from __future__ import annotations

from importlib import import_module
from pathlib import Path
from types import ModuleType
from typing import Any

from backend.app.agent_runtime.skills.base import Skill
from backend.app.agent_runtime.tools.base import Tool
from backend.app.plugins.runtime_context import PluginRuntimeContext


PLUGINS_ROOT = Path(__file__).resolve().parent


class PluginRegistryError(RuntimeError):
    """Raised when a Serenita plugin cannot be discovered safely."""


def discover_plugin_registries(root: str | Path = PLUGINS_ROOT) -> list[ModuleType]:
    """Load each immediate plugin package through its ``registry.py`` entrypoint."""

    plugin_root = Path(root).resolve()
    registries: list[ModuleType] = []
    for directory in sorted(plugin_root.iterdir(), key=lambda item: item.name):
        if (
            not directory.is_dir()
            or not (directory / "__init__.py").is_file()
            or not (directory / "registry.py").is_file()
        ):
            continue
        module = import_module(f"backend.app.plugins.{directory.name}.registry")
        plugin_id = str(getattr(module, "PLUGIN_ID", "")).strip()
        if plugin_id != directory.name:
            raise PluginRegistryError(
                f"插件目录名必须与 PLUGIN_ID 一致：{directory.name} != {plugin_id}"
            )
        if not callable(getattr(module, "build_skills", None)):
            raise PluginRegistryError(f"插件 {plugin_id} 缺少 build_skills()")
        registries.append(module)
    return registries


def build_builtin_skills() -> list[Skill]:
    """Collect Skills from every discovered Serenita plugin."""

    skills: list[Skill] = []
    seen: set[str] = set()
    for registry in discover_plugin_registries():
        for skill in registry.build_skills():
            if skill.name in seen:
                raise PluginRegistryError(f"重复的技能名称：{skill.name}")
            seen.add(skill.name)
            skills.append(skill)
    return skills




def build_available_tools(*, runtime_context: PluginRuntimeContext) -> list[Tool]:
    """Build all Tools from one generic, account-bound runtime context."""

    tools: list[Tool] = []
    seen: set[str] = set()
    for registry in discover_plugin_registries():
        builder = getattr(registry, "build_tools", None)
        if not callable(builder):
            continue
        for tool in builder(runtime_context=runtime_context):
            if tool.name in seen:
                raise PluginRegistryError(f"重复的工具名称：{tool.name}")
            seen.add(tool.name)
            tools.append(tool)
    return tools


def resolve_plugin_resource_refs(
    *, runtime_context: PluginRuntimeContext, resource_refs: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Resolve effect resources without teaching the harness plugin data types."""

    resolved: list[dict[str, Any]] = []
    for reference in resource_refs:
        for registry in discover_plugin_registries():
            resolver = getattr(registry, "resolve_resource", None)
            if not callable(resolver):
                continue
            resource = resolver(runtime_context=runtime_context, reference=reference)
            if resource is not None:
                resolved.append(resource)
                break
    return resolved


def resolve_plugin_resource_states(
    *, runtime_context: PluginRuntimeContext, resource_refs: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Resolve current resource availability without mutating timeline records."""

    resolved: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    registries = discover_plugin_registries()
    for reference in resource_refs:
        resource_type = str(reference.get("resource_type") or "").strip()
        resource_id = str(reference.get("resource_id") or "").strip()
        key = (str(reference.get("member_id") or ""), resource_type, resource_id)
        if not resource_type or not resource_id or key in seen:
            continue
        seen.add(key)
        for registry in registries:
            resolver = getattr(registry, "resolve_resource_state", None)
            if not callable(resolver):
                continue
            state = resolver(runtime_context=runtime_context, reference=reference)
            if state is not None:
                resolved.append(dict(state))
                break
    return resolved


def resolve_plugin_model_resource_refs(
    *, runtime_context: PluginRuntimeContext, resource_refs: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Resolve Tool-effect resource references for model input without routing by domain."""

    resolved: list[dict[str, Any]] = []
    for reference in resource_refs:
        item = None
        for registry in discover_plugin_registries():
            resolver = getattr(registry, "resolve_model_resource", None)
            if not callable(resolver):
                continue
            item = resolver(runtime_context=runtime_context, reference=reference)
            if item is not None:
                break
        if item is None:
            raise LookupError("工具返回了无法解析的模型资源引用。")
        resolved.append(dict(item))
    return resolved


def resolve_plugin_input_model_resources(
    *, runtime_context: PluginRuntimeContext, resource_refs: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Resolve attached plugin contexts that belong in the current model input."""

    resolved: list[dict[str, Any]] = []
    for reference in resource_refs:
        for registry in discover_plugin_registries():
            resolver = getattr(registry, "resolve_input_model_resource", None)
            if not callable(resolver):
                continue
            item = resolver(runtime_context=runtime_context, reference=reference)
            if item is not None:
                resolved.append(dict(item))
                break
    return resolved




