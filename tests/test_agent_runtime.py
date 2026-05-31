import unittest
from urllib.error import HTTPError


class AgentRuntimeTests(unittest.TestCase):
    def test_orchestrator_routes_task_to_registered_agent(self):
        from backend.app.agent_runtime.agents.base import AgentResult, BaseAgent
        from backend.app.agent_runtime.context import AgentContext
        from backend.app.agent_runtime.orchestrator import AgentOrchestrator

        class EchoAgent(BaseAgent):
            agent_id = "echo"
            name = "Echo Agent"
            supported_tasks = frozenset({"echo"})

            def run(self, context):
                return AgentResult(
                    agent_id=self.agent_id,
                    output={"text": context.input_text},
                    events=[],
                )

        orchestrator = AgentOrchestrator()
        orchestrator.register_agent(EchoAgent())

        result = orchestrator.run(
            AgentContext(
                account="demo_patient",
                task_type="echo",
                input_text="hello",
            )
        )

        self.assertEqual(result.agent_id, "echo")
        self.assertEqual(result.output, {"text": "hello"})

    def test_default_agent_registry_includes_future_health_agents(self):
        from backend.app.agent_runtime.agents import build_default_agents

        agent_ids = {agent.agent_id for agent in build_default_agents()}

        self.assertIn("report_analysis", agent_ids)
        self.assertIn("comprehensive_analysis", agent_ids)
        self.assertIn("lifestyle_advice", agent_ids)


class ToolMemoryProviderRegistryTests(unittest.TestCase):
    def test_tool_registry_returns_registered_tool_by_name(self):
        from backend.app.agent_runtime.tools.base import Tool, ToolResult
        from backend.app.agent_runtime.tools.registry import ToolRegistry

        class PingTool(Tool):
            name = "ping"
            description = "Return pong."

            def run(self, arguments):
                return ToolResult(name=self.name, output={"message": "pong"})

        registry = ToolRegistry()
        registry.register(PingTool())

        result = registry.get("ping").run({})

        self.assertEqual(result.output, {"message": "pong"})

    def test_memory_store_saves_and_lists_scoped_items(self):
        from backend.app.agent_runtime.memory.base import MemoryItem
        from backend.app.agent_runtime.memory.in_memory import InMemoryStore

        store = InMemoryStore()
        store.save(
            MemoryItem(
                account="demo_patient",
                namespace="conversation",
                content="ALT was elevated in the latest report.",
            )
        )

        items = store.list(account="demo_patient", namespace="conversation")

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].content, "ALT was elevated in the latest report.")

    def test_provider_registry_returns_registered_provider_by_id(self):
        from backend.app.providers.base import ModelProvider
        from backend.app.providers.registry import ProviderRegistry

        class DemoProvider(ModelProvider):
            provider_id = "demo"
            display_name = "Demo"

        registry = ProviderRegistry()
        registry.register(DemoProvider())

        provider = registry.get("demo")

        self.assertEqual(provider.provider_id, "demo")
        self.assertEqual(provider.display_name, "Demo")


class ModelProviderConnectionTests(unittest.TestCase):
    def test_connection_calls_models_endpoint_with_bearer_token(self):
        from backend.app.providers.base import ModelProvider

        class DemoProvider(ModelProvider):
            provider_id = "demo"
            display_name = "Demo"

        seen = {}

        class SuccessResponse:
            status = 200

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, traceback):
                return False

        def open_success(request, timeout):
            seen["url"] = request.full_url
            seen["authorization"] = request.get_header("Authorization")
            seen["timeout"] = timeout
            return SuccessResponse()

        result = DemoProvider(urlopen=open_success).test_connection(
            "http://provider.example/v1",
            "test-api-key",
        )

        self.assertTrue(result.reachable)
        self.assertEqual(result.message, "连接测试成功")
        self.assertEqual(seen["url"], "http://provider.example/v1/models")
        self.assertEqual(seen["authorization"], "Bearer test-api-key")
        self.assertEqual(seen["timeout"], 10)

    def test_connection_reports_authentication_failure(self):
        from backend.app.providers.base import ModelProvider

        class DemoProvider(ModelProvider):
            provider_id = "demo"
            display_name = "Demo"

        def open_unauthorized(request, timeout):
            raise HTTPError(request.full_url, 401, "Unauthorized", {}, None)

        result = DemoProvider(urlopen=open_unauthorized).test_connection(
            "http://provider.example",
            "bad-api-key",
        )

        self.assertFalse(result.reachable)
        self.assertEqual(result.message, "模型服务认证失败")

    def test_default_provider_registry_includes_default_base_urls(self):
        from backend.app.bootstrap import create_default_provider_registry

        registry = create_default_provider_registry()

        self.assertEqual(
            registry.get("openrouter").default_base_url,
            "https://openrouter.ai/api/v1",
        )
        self.assertEqual(
            registry.get("deepseek").default_base_url,
            "https://api.deepseek.com",
        )
        self.assertEqual(
            registry.get("aliyun_bailian").default_base_url,
            "https://dashscope.aliyuncs.com/compatible-mode/v1",
        )


if __name__ == "__main__":
    unittest.main()
