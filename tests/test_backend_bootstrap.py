import unittest


class BackendBootstrapTests(unittest.TestCase):
    def test_application_container_wires_runtime_boundaries(self):
        from backend.app.bootstrap import create_application_container

        container = create_application_container()

        self.assertIsNotNone(container.orchestrator)
        self.assertIsNotNone(container.tool_registry)
        self.assertIsNotNone(container.memory_store)
        self.assertEqual(container.provider_registry.get("openrouter").display_name, "OpenRouter")
        self.assertEqual(container.provider_registry.get("deepseek").display_name, "深度求索")
        self.assertEqual(container.provider_registry.get("aliyun_bailian").display_name, "阿里云百炼")


if __name__ == "__main__":
    unittest.main()
