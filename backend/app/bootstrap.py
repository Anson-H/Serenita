from dataclasses import dataclass

from backend.app.agent_runtime.agents import build_default_agents
from backend.app.agent_runtime.memory.in_memory import InMemoryStore
from backend.app.agent_runtime.orchestrator import AgentOrchestrator
from backend.app.agent_runtime.tools.registry import ToolRegistry
from backend.app.providers.aliyun_bailian import AliyunBailianProvider
from backend.app.providers.deepseek import DeepSeekProvider
from backend.app.providers.openrouter import OpenRouterProvider
from backend.app.providers.registry import ProviderRegistry


@dataclass(frozen=True)
class ApplicationContainer:
    orchestrator: AgentOrchestrator
    provider_registry: ProviderRegistry
    tool_registry: ToolRegistry
    memory_store: InMemoryStore


def create_default_provider_registry() -> ProviderRegistry:
    registry = ProviderRegistry()
    registry.register(OpenRouterProvider())
    registry.register(DeepSeekProvider())
    registry.register(AliyunBailianProvider())
    return registry


def create_application_container() -> ApplicationContainer:
    return ApplicationContainer(
        orchestrator=AgentOrchestrator(build_default_agents()),
        provider_registry=create_default_provider_registry(),
        tool_registry=ToolRegistry(),
        memory_store=InMemoryStore(),
    )
