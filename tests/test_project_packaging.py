import pathlib
import unittest


class ProjectPackagingTests(unittest.TestCase):
    def test_hatch_wheel_build_selects_backend_package(self):
        pyproject_path = pathlib.Path(__file__).resolve().parents[1] / "pyproject.toml"
        pyproject = pyproject_path.read_text(encoding="utf-8")

        self.assertIn("[tool.hatch.build.targets.wheel]", pyproject)
        self.assertIn('packages = ["backend"]', pyproject)


if __name__ == "__main__":
    unittest.main()
